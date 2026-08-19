"""A spending limit that belongs to a reader, and the approvals that clear it.

Bill Densmore's, from the Clickshare documentation of the 1990s and raised again
on 18 Aug 2026: a reader names a figure, and anything above it asks them first.

It could not be built until now, and the reason is worth keeping. A threshold
belongs to a person, and until #53 no party in this network could identify one:
the agent receives a pairwise identifier that differs at every publisher, so the
only rules it could apply were rules for everybody at once. Now that the home
base can resolve its own readers, a limit can be theirs.

== Why the limit is measured against the retail price ==

The publisher's asking price is not what the reader pays. Their home base adds
its margin, and the figure the reader is billed -- and therefore the only figure
a reader's limit can sensibly refer to -- is `wholesale x markup`. A threshold
enforced at the publisher would be measured against the wrong number, which is
the substantive reason this belongs at the home base rather than in the plugin.

== Where the limit lives ==

On the reader's account at their home base, as a Keycloak user attribute. It is
their preference, held by the organisation they have the account with, and it
survives this service being restarted or replaced. Nothing about it reaches the
publisher or the exchange: they see only that a purchase was, or was not,
authorised.

== Approvals ==

An approval is deliberately narrow: this reader, this resource, this price, for
a few minutes. It is not a raised limit and not a standing consent. If the same
reader meets a different article above their limit, they are asked again, which
is the entire point of having asked in the first place.

Held in memory, so a restart forgets them and a reader is asked once more. That
is the right way for this to fail: forgetting an approval costs a click, while
remembering one that was never given spends somebody's money.
"""
from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger("asp-agent.thresholds")

ATTRIBUTE = "newshare_threshold"

# Per-publisher overrides: {"ITEGA-PA-0001": null} to never ask about a
# publication, or {"ITEGA-PA-0001": "0.50"} to ask only above a different
# figure there. The cheapest useful shape of limit, because the agent already
# receives pubMbrId on every quote -- "buy anything from my own paper, ask me
# about the rest" costs no new machinery at all.
BY_SOURCE = "newshare_threshold_by_source"

# A spending cap over a period, and its running tally. Kept on the reader's
# account rather than in this process: a cap that resets when a service
# restarts is not a cap, it is a suggestion.
PERIOD_CAP = "newshare_period_cap"        # e.g. "2.00|week"
PERIOD_SPENT = "newshare_period_spent"    # e.g. "0.35|2026-W34"

# How long a reader's approval stands. Long enough to return to the article,
# short enough that a shared machine does not carry consent to the next person.
APPROVAL_TTL = 600


class Thresholds:
    """Reads a reader's limit, and remembers what they have approved."""

    def __init__(self, base_url: str, realm: str, username: str, password: str) -> None:
        self._base = base_url.rstrip("/")
        self._realm = realm
        self._username = username
        self._password = password
        self._approvals: dict[tuple[str, str], tuple[float, float]] = {}

    async def _token(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{self._base}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self._username,
                "password": self._password,
            },
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])

    @staticmethod
    def _period_key(period: str, now: time.struct_time | None = None) -> str:
        """Which window we are in. Changing key means the tally starts again."""
        t = now or time.gmtime()
        if period == "day":
            return time.strftime("%Y-%m-%d", t)
        if period == "month":
            return time.strftime("%Y-%m", t)
        return time.strftime("%Y-W%W", t)          # week, the default

    async def _attributes(self, local_sub: str) -> dict[str, list[str]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token = await self._token(client)
            resp = await client.get(
                f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json().get("attributes") or {}

    async def rules_for(self, local_sub: str) -> dict[str, Any]:
        """Everything this reader has asked for, in one read.

        One call rather than four: this runs on the buying path, in front of a
        reader waiting for an article.
        """
        try:
            attrs = await self._attributes(local_sub)
        except Exception as exc:
            # Unreadable rules are treated as no rules, never as a limit of
            # zero. A directory outage must not become a network-wide refusal.
            logger.warning("could not read rules for %s: %s", local_sub[:8], exc)
            return {"limit": None, "by_source": {}, "cap": None, "period": "week", "spent": Decimal(0)}

        def first(key: str) -> str:
            values = attrs.get(key) or []
            return str(values[0]) if values else ""

        limit = None
        if first(ATTRIBUTE):
            try:
                limit = Decimal(first(ATTRIBUTE))
            except Exception:
                logger.warning("unreadable threshold for %s", local_sub[:8])

        by_source: dict[str, Decimal | None] = {}
        if first(BY_SOURCE):
            try:
                for pub, value in json.loads(first(BY_SOURCE)).items():
                    by_source[str(pub)] = None if value is None else Decimal(str(value))
            except Exception:
                logger.warning("unreadable per-source limits for %s", local_sub[:8])

        cap, period = None, "week"
        if first(PERIOD_CAP):
            try:
                amount, _, window = first(PERIOD_CAP).partition("|")
                cap = Decimal(amount)
                period = window or "week"
            except Exception:
                logger.warning("unreadable period cap for %s", local_sub[:8])

        spent = Decimal(0)
        if first(PERIOD_SPENT):
            try:
                amount, _, key = first(PERIOD_SPENT).partition("|")
                # A tally from a window that has closed is not this window's.
                if key == self._period_key(period):
                    spent = Decimal(amount)
            except Exception:
                pass

        return {"limit": limit, "by_source": by_source, "cap": cap,
                "period": period, "spent": spent}

    def effective_limit(self, rules: dict[str, Any], pub_mbr_id: str) -> Decimal | None:
        """The figure that applies at this publication.

        A per-source entry wins over the general one, including when it is null
        -- which is how a reader says "never ask me about my own paper".
        """
        by_source = rules.get("by_source") or {}
        if pub_mbr_id in by_source:
            return by_source[pub_mbr_id]
        return rules.get("limit")

    async def record_spend(self, local_sub: str, retail: Decimal) -> None:
        """Add to this window's tally, on the reader's own account.

        Written through rather than held here, because a cap that forgets when a
        container restarts is not a cap. One write per purchase is affordable at
        the volumes this network deals in, and if it ever is not, the fix is a
        store rather than forgetting.
        """
        try:
            rules = await self.rules_for(local_sub)
            period = rules.get("period") or "week"
            total = (rules.get("spent") or Decimal(0)) + retail
            async with httpx.AsyncClient(timeout=10.0) as client:
                token = await self._token(client)
                headers = {"Authorization": f"Bearer {token}"}
                current = await client.get(
                    f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                    headers=headers)
                current.raise_for_status()
                user = current.json()
                attributes = user.get("attributes") or {}
                attributes[PERIOD_SPENT] = [f"{total}|{self._period_key(period)}"]
                user["attributes"] = attributes
                resp = await client.put(
                    f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                    headers=headers, json=user)
                resp.raise_for_status()
        except Exception as exc:
            # Never let bookkeeping refuse a purchase the reader has already
            # been granted. An undercounted tally is a smaller wrong than an
            # article withheld after it was authorised.
            logger.warning("could not record spend for %s: %s", local_sub[:8], exc)

    async def limit_for(self, local_sub: str) -> Decimal | None:
        """The reader's own limit, or None if they have not set one.

        None means no limit rather than a limit of zero. A reader who has never
        heard of this feature must not find their reading stopped by it.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token = await self._token(client)
                resp = await client.get(
                    f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                values = (resp.json().get("attributes") or {}).get(ATTRIBUTE) or []
        except Exception as exc:
            # A directory that cannot be reached must not silently become a
            # limit of zero, which would stop every purchase for every reader.
            logger.warning("could not read a threshold for %s: %s", local_sub[:8], exc)
            return None

        if not values:
            return None
        try:
            return Decimal(str(values[0]))
        except Exception:
            logger.warning("unreadable threshold %r for %s", values[0], local_sub[:8])
            return None

    async def set_limit(self, local_sub: str, amount: Decimal | None) -> None:
        """Set or clear a reader's limit. Theirs to change, nobody else's."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            token = await self._token(client)
            headers = {"Authorization": f"Bearer {token}"}
            current = await client.get(
                f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                headers=headers,
            )
            current.raise_for_status()
            user = current.json()
            attributes = user.get("attributes") or {}
            if amount is None:
                attributes.pop(ATTRIBUTE, None)
            else:
                attributes[ATTRIBUTE] = [str(amount)]

            # The whole representation goes back, not just the attributes.
            #
            # Keycloak's declarative User Profile validates what it is sent as
            # if it were the complete user, so a partial update reads as a user
            # who has lost their email address:
            #
            #     {"field":"email","errorMessage":"error-user-attribute-required"}
            #
            # which is a 400 that says nothing about the attribute being set.
            user["attributes"] = attributes
            resp = await client.put(
                f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                headers=headers,
                json=user,
            )
            resp.raise_for_status()

    async def _write(self, local_sub: str, key: str, value: str | None) -> None:
        """Set or remove one attribute, sending Keycloak the whole user.

        A partial update is validated as if it were the complete user, so
        sending attributes alone fails with a complaint that the email address
        is missing -- a 400 naming a field nobody touched. #29.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            token = await self._token(client)
            headers = {"Authorization": f"Bearer {token}"}
            current = await client.get(
                f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                headers=headers)
            current.raise_for_status()
            user = current.json()
            attributes = user.get("attributes") or {}
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = [value]
            user["attributes"] = attributes
            resp = await client.put(
                f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                headers=headers, json=user)
            resp.raise_for_status()

    async def set_source_limit(self, local_sub: str, pub_mbr_id: str,
                               amount: Decimal | None, clear: bool = False) -> None:
        """A figure for one publication, or none at all for it.

        None is meaningful here and is not the same as absent: absent means
        "use my general limit", None means "never ask me about this one".
        """
        rules = await self.rules_for(local_sub)
        by_source = dict(rules.get("by_source") or {})
        if clear:
            by_source.pop(pub_mbr_id, None)
        else:
            by_source[pub_mbr_id] = amount
        if by_source:
            payload = json.dumps({k: (None if v is None else str(v))
                                  for k, v in by_source.items()})
            await self._write(local_sub, BY_SOURCE, payload)
        else:
            await self._write(local_sub, BY_SOURCE, None)

    async def set_cap(self, local_sub: str, amount: Decimal | None, period: str) -> None:
        """A ceiling on the whole period, and which period that is.

        Changing the period resets the tally, because a total counted over a
        week is not a total over a day and pretending otherwise would either
        overcharge the reader's patience or undercount their spending.
        """
        if amount is None:
            await self._write(local_sub, PERIOD_CAP, None)
            await self._write(local_sub, PERIOD_SPENT, None)
            return
        await self._write(local_sub, PERIOD_CAP, f"{amount}|{period}")
        await self._write(local_sub, PERIOD_SPENT, f"0|{self._period_key(period)}")

    # ── Approvals ─────────────────────────────────────────────────────

    def approve(self, local_sub: str, resource_id: str, retail: Decimal) -> None:
        self._approvals[(local_sub, resource_id)] = (time.time(), float(retail))

    def approved(self, local_sub: str, resource_id: str, retail: Decimal) -> bool:
        """Has this reader agreed to this article, at this price, just now?

        The price is part of the question. An approval given for four cents does
        not authorise forty, and a publisher that raised its price between the
        asking and the buying should meet the reader again rather than the
        reader's earlier consent.
        """
        entry = self._approvals.get((local_sub, resource_id))
        if entry is None:
            return False
        when, agreed = entry
        if time.time() - when > APPROVAL_TTL:
            self._approvals.pop((local_sub, resource_id), None)
            return False
        return abs(agreed - float(retail)) < 0.00005

    def forget(self, local_sub: str, resource_id: str) -> None:
        self._approvals.pop((local_sub, resource_id), None)
