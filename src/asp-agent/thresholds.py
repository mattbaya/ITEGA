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

import logging
import time
from decimal import Decimal

import httpx

logger = logging.getLogger("asp-agent.thresholds")

ATTRIBUTE = "newshare_threshold"

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
            resp = await client.put(
                f"{self._base}/admin/realms/{self._realm}/users/{local_sub}",
                headers=headers,
                json={"attributes": attributes},
            )
            resp.raise_for_status()

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
