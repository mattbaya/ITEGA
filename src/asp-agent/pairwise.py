"""Resolve a reader's pairwise identifiers back to the reader — at the home base only.

Every other party in this network sees a reader as an opaque value that differs
at every publisher, and cannot do better. The home base can, because it issued
those values, and that asymmetry is the whole architecture: the map exists in
exactly one place, held by the organisation the reader already trusts with their
name.

Bill Densmore asked for two things on 18 Aug 2026 — a reader's history across the
network (#28), and a spending threshold the reader sets for themselves (#29).
Both need this and nothing else does, so his two requests are one build.

== The derivation ==

Keycloak's oidc-sha256-pairwise-sub-mapper, reproduced exactly:

    sub = UUID.nameUUIDFromBytes( SHA256( sector + localSub + salt ) )

`salt` is each client's own `pairwiseSubAlgorithmSalt`. `sector` is the host of
the client's redirect URI, because no `sectorIdentifierUri` is configured -- so
every publisher in this deployment shares a sector and the salt is what
separates them. Anyone changing a redirect URI should know it would silently
re-issue every reader a new identity at that publisher.

`nameUUIDFromBytes` is Java's MD5-based version 3, which is why every identifier
in this network has a 3 at the head of its third group.

== Why this file distrusts itself ==

A wrong derivation does not raise anything. It produces an index that is empty,
or -- far worse -- one that maps a reader onto another reader's rows. An empty
history is indistinguishable from a reader who has read nothing, and this
project's recurring defect is exactly that: a check that cannot observe what it
claims (#18, #43, #50, #55).

So the index is never trusted on its own say-so. Every quote that arrives
carries a real pairwise identifier, minted by Keycloak, and `observe()` records
whether this file can account for it. Until enough of those have resolved,
`trustworthy()` is False and the endpoints built on this refuse to answer. The
proof that the arithmetic is right comes from live traffic rather than from a
fixture agreeing with itself.

`infra/ppid-derivation-test.py` checks the same derivation from outside, against
identifiers two publisher sites recorded independently.
"""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
import uuid
from typing import Any

import httpx

logger = logging.getLogger("asp-agent.pairwise")

# How long a built index is kept before it is rebuilt. Readers sign up rarely;
# a miss rebuilds immediately anyway, so this only bounds staleness for values
# that were never valid.
INDEX_TTL = 900

# Live identifiers that must resolve before the index is believed. One is
# enough to prove the arithmetic; a second guards against a coincidence.
CONFIRMATIONS_REQUIRED = 2


def pairwise_sub(sector: str, local_sub: str, salt: str) -> str:
    """One identifier, as Keycloak would mint it."""
    digest = hashlib.sha256((sector + local_sub + salt).encode()).digest()
    return str(uuid.UUID(bytes=hashlib.md5(digest).digest(), version=3))


class PairwiseIndex:
    """networkUserId -> the home base's own user id, for its own readers only.

    Holds nothing about anybody else's readers and cannot: the salts are its
    realm's, and the user list is its own.
    """

    def __init__(self, base_url: str, realm: str, username: str, password: str) -> None:
        self._base = base_url.rstrip("/")
        self._realm = realm
        self._username = username
        self._password = password
        self._index: dict[str, str] = {}
        self._clients: list[tuple[str, str, str]] = []   # (client_id, sector, salt)
        self._built_at = 0.0
        self._seen = 0
        self._resolved = 0

    # ── Keycloak ──────────────────────────────────────────────────────

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

    async def _clients_with_pairwise(self, client: httpx.AsyncClient, token: str) -> list[tuple[str, str, str]]:
        """Every client that mints pairwise identifiers, with what it mints them from."""
        headers = {"Authorization": f"Bearer {token}"}
        resp = await client.get(
            f"{self._base}/admin/realms/{self._realm}/clients", headers=headers
        )
        resp.raise_for_status()

        out: list[tuple[str, str, str]] = []
        for c in resp.json():
            mappers = c.get("protocolMappers") or []
            pw = next(
                (m for m in mappers
                 if "pairwise" in str(m.get("protocolMapper", "")).lower()),
                None,
            )
            if pw is None:
                continue
            cfg = pw.get("config", {})
            salt = cfg.get("pairwiseSubAlgorithmSalt")
            if not salt:
                continue

            # Keycloak falls back to the redirect URI's host when no sector
            # identifier is configured. Reproduce that rather than assume one.
            sector = cfg.get("sectorIdentifierUri") or ""
            if sector:
                sector = urllib.parse.urlparse(sector).netloc or sector
            else:
                redirects = c.get("redirectUris") or []
                if not redirects:
                    logger.warning(
                        "client %s mints pairwise ids but has no redirect URI; skipped",
                        c.get("clientId"),
                    )
                    continue
                sector = urllib.parse.urlparse(redirects[0]).netloc

            out.append((str(c.get("clientId")), sector, str(salt)))
        return out

    async def _users(self, client: httpx.AsyncClient, token: str) -> list[str]:
        headers = {"Authorization": f"Bearer {token}"}
        users: list[str] = []
        first = 0
        while True:
            resp = await client.get(
                f"{self._base}/admin/realms/{self._realm}/users",
                headers=headers,
                params={"first": first, "max": 200, "briefRepresentation": "true"},
            )
            resp.raise_for_status()
            page = resp.json()
            if not page:
                break
            users.extend(str(u["id"]) for u in page if u.get("id"))
            if len(page) < 200:
                break
            first += 200
        return users

    # ── Index ─────────────────────────────────────────────────────────

    async def build(self) -> None:
        """Compute every identifier this home base has ever minted, and invert it.

        Cost is users x clients, which for a home base of any plausible size is
        trivial arithmetic and two admin calls. A network of millions would want
        this stored at issue time instead; a pilot of fifty does not.
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._token(client)
            self._clients = await self._clients_with_pairwise(client, token)
            users = await self._users(client, token)

        index: dict[str, str] = {}
        for local_sub in users:
            for _client_id, sector, salt in self._clients:
                index[pairwise_sub(sector, local_sub, salt)] = local_sub

        self._index = index
        self._built_at = time.time()
        logger.info(
            "pairwise index: %d readers x %d publishers = %d identifiers",
            len(users), len(self._clients), len(index),
        )

    async def _fresh(self) -> None:
        if not self._index or time.time() - self._built_at > INDEX_TTL:
            await self.build()

    async def resolve(self, network_user_id: str) -> str | None:
        """Which of this home base's readers carries that identifier."""
        await self._fresh()
        hit = self._index.get(network_user_id)
        if hit is None:
            # A reader who signed up since the index was built looks exactly
            # like a wrong derivation. Rebuild once before believing the miss.
            await self.build()
            hit = self._index.get(network_user_id)
        return hit

    async def identifiers_for(self, local_sub: str) -> dict[str, str]:
        """Every identifier one reader carries, by publisher client id."""
        await self._fresh()
        return {
            client_id: pairwise_sub(sector, local_sub, salt)
            for client_id, sector, salt in self._clients
        }

    # ── Self-check ────────────────────────────────────────────────────

    def observe(self, network_user_id: str) -> None:
        """Record whether a real, Keycloak-minted identifier was accounted for.

        This is the only evidence that matters. Everything else in this file
        agrees with itself by construction.
        """
        self._seen += 1
        if network_user_id in self._index:
            self._resolved += 1

    def trustworthy(self) -> bool:
        return self._resolved >= CONFIRMATIONS_REQUIRED

    def status(self) -> dict[str, Any]:
        return {
            "identifiers": len(self._index),
            "publishers": len(self._clients),
            "live_identifiers_seen": self._seen,
            "live_identifiers_resolved": self._resolved,
            "trustworthy": self.trustworthy(),
        }
