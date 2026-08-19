"""Prove the caller is the reader they claim to be, before answering about them.

This exists because the endpoints it guards did not have it. Built to demonstrate
that a reader's history and spending limit worked, they were tested by calling
them with an identifier that happened to be to hand -- which is exactly what an
attacker has. Nothing in that testing distinguished "the mechanism works" from
"the mechanism works for anybody who asks" (#62).

The history endpoint was the serious one. Every publisher already stores its own
readers' identifiers -- the plugin writes `newshare_network_user_id` into
`wp_usermeta` for each of them -- so a publisher could take one it legitimately
holds and ask that reader's home base where else they read. Pairwise identifiers
stop publishers correlating with each other; an unauthenticated history endpoint
hands one of them the answer, from the only party in the network able to compute
it.

Two mechanisms, because the two situations differ:

**A bearer sessionToken**, for a reader asking about themselves. The exchange
already issues one to every signed-in reader, RS256, carrying `networkUserId`.
Verified against the exchange's published keys, and the claim must match the
reader being asked about. Nothing new is issued and no new secret exists.

**A single-use nonce**, for the approval link. That link is followed by a browser
arriving from a publisher's page, where there is no good way to carry a bearer
token and no good place to put one -- a token in a URL ends up in every access
log between here and the reader. So the agent mints an unguessable nonce when it
holds a purchase, and only the party that received that quote can act on it,
once, before it expires.
"""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JWTError

logger = logging.getLogger("asp-agent.reader_auth")

# Long enough to walk from a publisher's page to the approval and back, short
# enough that a link left in a shared browser's history is worth nothing.
NONCE_TTL = 600

# How long the agent trusts its answer about who a publisher key belongs to.
PUBLISHER_CACHE_TTL = 300


class ReaderAuth:
    """Verifies a reader's session token, and mints one-shot approval nonces."""

    def __init__(self, als_base_url: str) -> None:
        self._jwks_url = als_base_url.rstrip("/") + "/.well-known/jwks.json"
        self._jwks: dict[str, Any] | None = None
        self._fetched = 0.0
        self._nonces: dict[str, tuple[float, str, str, float]] = {}
        self._publishers: dict[str, tuple[float, str]] = {}

    async def _keys(self) -> dict[str, Any] | None:
        # Cached, but re-fetched on a miss by the caller below: a key rotation
        # must not lock every reader out until this service restarts.
        if self._jwks is None or time.time() - self._fetched > 3600:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(self._jwks_url)
                    resp.raise_for_status()
                    self._jwks = resp.json()
                    self._fetched = time.time()
            except Exception as exc:
                logger.warning("could not fetch the exchange's keys: %s", exc)
                return None
        return self._jwks

    async def reader_from(self, authorization: str | None) -> str | None:
        """The networkUserId this bearer token actually proves, or None.

        Returns None for every failure without distinguishing them to the
        caller. A caller learning *why* their forgery was rejected is a caller
        being helped to forge a better one.
        """
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        token = authorization.split(" ", 1)[1].strip()

        keys = await self._keys()
        if keys is None:
            return None

        for attempt in range(2):
            try:
                claims = jwt.decode(
                    token,
                    keys,
                    algorithms=["RS256"],
                    options={"verify_aud": False},
                )
                network_user_id = str(claims.get("networkUserId", ""))
                return network_user_id or None
            except JWTError as exc:
                # One retry with fresh keys, in case the exchange rotated them.
                if attempt == 0:
                    self._jwks = None
                    keys = await self._keys()
                    if keys is not None:
                        continue
                logger.info("rejected a session token: %s", exc)
                return None
        return None

    # ── Publisher identity ────────────────────────────────────────────

    async def publisher_from(self, api_key: str | None, logging_url: str) -> str | None:
        """Which publisher this API key belongs to, according to the exchange.

        The agent does not hold publisher keys and must not: they are ITEGA's to
        issue and revoke. So it asks the exchange, using the endpoint built for
        publishers to check their own credentials, and caches the answer briefly
        -- this sits on the buying path, in front of a reader waiting for an
        article, and a network round trip per quote would be felt.

        A cache miss costs one request. A revoked key keeps working for at most
        the cache lifetime, which is the trade being made deliberately: the
        alternative is charging every reader's page view an extra hop.
        """
        if not api_key:
            return None

        cached = self._publishers.get(api_key)
        if cached and time.time() - cached[0] < PUBLISHER_CACHE_TTL:
            return cached[1]

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    logging_url.rstrip("/") + "/whoami"
                    if logging_url.rstrip("/").endswith("/log")
                    else logging_url.rstrip("/") + "/log/whoami",
                    headers={"X-API-Key": api_key},
                )
        except Exception as exc:
            # The exchange being unreachable must not stop a home base buying
            # for its readers. Unknown, not refused -- the caller decides.
            logger.warning("could not check a publisher key: %s", exc)
            return None

        if resp.status_code != 200:
            return None
        pub_mbr_id = str(resp.json().get("pub_mbr_id", ""))
        if pub_mbr_id:
            self._publishers[api_key] = (time.time(), pub_mbr_id)
        return pub_mbr_id or None

    # ── Approval nonces ───────────────────────────────────────────────

    def mint(self, network_user_id: str, resource_id: str, retail: float) -> str:
        """A one-shot handle for approving one purchase.

        The nonce stands in for the reader's identifier in the link, so the link
        itself grants nothing beyond the single approval it was minted for.
        """
        nonce = secrets.token_urlsafe(24)
        self._nonces[nonce] = (time.time(), network_user_id, resource_id, retail)
        self._sweep()
        return nonce

    def spend(self, nonce: str) -> tuple[str, str, float] | None:
        """Redeem it, once. Returns (networkUserId, resourceId, retail)."""
        entry = self._nonces.pop(nonce, None)
        if entry is None:
            return None
        when, network_user_id, resource_id, retail = entry
        if time.time() - when > NONCE_TTL:
            return None
        return network_user_id, resource_id, retail

    def _sweep(self) -> None:
        cutoff = time.time() - NONCE_TTL
        for nonce, (when, *_rest) in list(self._nonces.items()):
            if when < cutoff:
                self._nonces.pop(nonce, None)
