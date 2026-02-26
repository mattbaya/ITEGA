"""
ALS Auth Service — JWT signing and validation utilities.

Handles two distinct key sets:
  1. Keycloak JWKS (fetched remotely, cached) — used to verify ID tokens
     received from the home base during the OIDC callback.
  2. ALS RSA key pair (loaded from disk) — used to sign and verify
     ALS-issued session tokens.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from jose import JWTError, jwt
from jose.backends import RSAKey

logger = logging.getLogger("als-auth.jwt")


# ── Keycloak JWKS cache ──────────────────────────────────────────────

class JWKSCache:
    """Fetches and caches Keycloak's JWKS endpoint with a configurable TTL."""

    def __init__(self, jwks_url: str, ttl: int = 300) -> None:
        self._jwks_url = jwks_url
        self._ttl = ttl
        self._keys: dict[str, Any] | None = None
        self._last_refresh: float = 0.0

    async def get_keys(self) -> dict[str, Any]:
        """Return cached JWKS, refreshing if stale or missing."""
        now = time.time()
        if self._keys is None or (now - self._last_refresh) > self._ttl:
            await self._refresh()
        return self._keys  # type: ignore[return-value]

    async def _refresh(self) -> None:
        logger.info("Refreshing JWKS from %s", self._jwks_url)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._jwks_url)
                resp.raise_for_status()
                self._keys = resp.json()
                self._last_refresh = time.time()
                logger.info(
                    "JWKS refreshed — %d key(s) loaded",
                    len(self._keys.get("keys", [])),
                )
        except httpx.HTTPError as exc:
            logger.error("Failed to refresh JWKS: %s", exc)
            if self._keys is None:
                raise RuntimeError("Cannot start without JWKS") from exc
            # On refresh failure, keep stale keys rather than crashing.

    async def force_refresh(self) -> None:
        """Force an immediate refresh (e.g. after a signature failure)."""
        self._last_refresh = 0.0
        await self._refresh()


# ── Keycloak ID-token verification ───────────────────────────────────

async def verify_keycloak_id_token(
    token: str,
    jwks_cache: JWKSCache,
    issuer: str,
    audience: str,
) -> dict[str, Any]:
    """
    Verify a Keycloak-issued ID token using the cached JWKS.

    Returns the decoded claims dict on success; raises JWTError on failure.
    """
    jwks = await jwks_cache.get_keys()
    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"verify_at_hash": False},
        )
        return claims
    except JWTError:
        # Key may have rotated — force refresh and retry once.
        logger.warning("ID-token verification failed; forcing JWKS refresh")
        await jwks_cache.force_refresh()
        jwks = await jwks_cache.get_keys()
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"verify_at_hash": False},
        )
        return claims


# ── ALS session-token signing / verification ─────────────────────────

def sign_session_token(
    claims: dict[str, Any],
    private_key_pem: str,
) -> str:
    """
    Sign an ALS session token with the ALS private RSA key.

    The caller is responsible for populating all required claims
    (iss, sub, aud, exp, iat, custom network fields).
    """
    return jwt.encode(claims, private_key_pem, algorithm="RS256")


def verify_session_token(
    token: str,
    public_key_pem: str,
    issuer: str,
) -> dict[str, Any]:
    """
    Verify an ALS-issued session token.

    Returns decoded claims on success; raises JWTError on failure.
    """
    return jwt.decode(
        token,
        public_key_pem,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False},
    )
