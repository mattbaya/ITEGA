"""
ALS Auth Service — JWT signing and validation utilities.

This module manages two distinct cryptographic key sets used in the Newshare
federated authentication flow:

  1. **Keycloak JWKS (remote, cached)** — The home base (Keycloak) publishes
     its public keys at a JWKS endpoint.  We fetch and cache them so that
     we can verify the ID tokens Keycloak issues after user authentication.
     The cache has a configurable TTL (default 5 min) to balance freshness
     against Keycloak load.  If verification fails, we force a JWKS refresh
     and retry once — this handles key rotation transparently.

  2. **ALS RSA key pair (local, on-disk)** — The ALS has its own RSA-2048+
     key pair used to sign session tokens (JWTs) that it issues to publishers.
     Publishers can verify these tokens either:
       a. By calling POST /auth/validate (online verification), or
       b. By fetching the ALS JWKS from /.well-known/jwks.json and verifying
          locally (offline verification — preferred for latency).

All tokens use the RS256 (RSASSA-PKCS1-v1_5 + SHA-256) algorithm, per the
Newshare spec and OIDC best practices.
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
#
# The home base (Keycloak) signs ID tokens with its private RSA key and
# publishes the corresponding public key(s) at a JWKS URL.  This cache
# fetches that JWKS and holds it in memory, re-fetching when the TTL
# expires.  This avoids hitting Keycloak on every token verification.
#
# Key rotation handling:
#   If a token's signature fails to verify, the caller should call
#   force_refresh() and retry.  This covers the case where Keycloak has
#   rotated keys but our cache still holds the old JWKS.

class JWKSCache:
    """
    Fetches and caches Keycloak's JWKS endpoint with a configurable TTL.

    Thread-safety note: This class is used in an async (single-threaded)
    context, so no locking is needed.  If adapted for multi-threaded use,
    add a lock around _refresh().
    """

    def __init__(self, jwks_url: str, ttl: int = 300) -> None:
        self._jwks_url = jwks_url    # Full URL to Keycloak's JWKS endpoint
        self._ttl = ttl              # Cache lifetime in seconds
        self._keys: dict[str, Any] | None = None   # Cached JWKS payload
        self._last_refresh: float = 0.0             # Timestamp of last fetch

    async def get_keys(self) -> dict[str, Any]:
        """Return cached JWKS, refreshing if stale or missing."""
        now = time.time()
        if self._keys is None or (now - self._last_refresh) > self._ttl:
            await self._refresh()
        return self._keys  # type: ignore[return-value]

    async def _refresh(self) -> None:
        """Fetch the JWKS from Keycloak and update the cache."""
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
                # First fetch ever failed — cannot proceed without any keys.
                raise RuntimeError("Cannot start without JWKS") from exc
            # On subsequent refresh failure, keep stale keys rather than
            # crashing.  The next get_keys() call will retry after TTL.

    async def force_refresh(self) -> None:
        """Force an immediate refresh (e.g. after a signature failure)."""
        self._last_refresh = 0.0
        await self._refresh()


# ── Keycloak ID-token verification ───────────────────────────────────
#
# Called during the /auth/callback flow after the ALS exchanges the
# authorization code with Keycloak and receives an ID token.  We verify
# the token's RS256 signature against the cached JWKS, and also check
# the ``iss`` (must match the Keycloak realm URL) and ``aud`` (must
# match the publisher's client_id).
#
# The ``verify_at_hash`` option is disabled because the ALS receives
# the ID token directly from the Keycloak token endpoint (not via
# front-channel), so at_hash verification is not required per OIDC spec.

async def verify_keycloak_id_token(
    token: str,
    jwks_cache: JWKSCache,
    issuer: str,
    audience: str,
) -> dict[str, Any]:
    """
    Verify a Keycloak-issued ID token using the cached JWKS.

    Returns the decoded claims dict on success; raises ``JWTError`` on
    failure.  If the first verification attempt fails (possibly due to
    key rotation), forces a JWKS refresh and retries exactly once.
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
        # Key may have rotated at the home base — force a JWKS refresh
        # and retry once.  If this also fails, the JWTError propagates
        # to the caller (which returns 401 to the user).
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
#
# These functions use the ALS's own RSA key pair (separate from Keycloak's).
# The private key signs session tokens issued after a successful OIDC
# callback; the public key is used by /auth/validate and published via
# /.well-known/jwks.json so publishers can verify tokens offline.

# Must match the "kid" published in the ALS JWKS.
ALS_SIGNING_KID = "als-signing-key-1"


def sign_session_token(
    claims: dict[str, Any],
    private_key_pem: str,
) -> str:
    """
    Sign an ALS session token with the ALS private RSA key.

    The caller is responsible for populating all required claims:
      - Standard OIDC: iss, sub, aud, exp, iat
      - Newshare custom: networkUserId, homeBaseId, networkGroupId,
        pubMbrId, sessionId

    The header carries a ``kid`` matching the entry published at
    /.well-known/jwks.json. Without it a relying party holding a key set has no
    way to choose a key: firebase/php-jwt refuses the token outright with
    ``"kid" empty, unable to lookup correct key``, which is a 403 at the last
    step of signing in. It also makes key rotation possible, since old and new
    keys can be published together and told apart.

    Returns the compact JWS string (header.payload.signature).
    """
    return jwt.encode(
        claims,
        private_key_pem,
        algorithm="RS256",
        headers={"kid": ALS_SIGNING_KID},
    )


def verify_session_token(
    token: str,
    public_key_pem: str,
    issuer: str,
) -> dict[str, Any]:
    """
    Verify an ALS-issued session token using the ALS public key.

    Checks the RS256 signature, ``exp`` (expiry), and ``iss`` (issuer).
    Audience (``aud``) verification is disabled because the /auth/validate
    endpoint serves all publishers; per-publisher audience checks are the
    responsibility of the calling publisher plugin.

    Returns decoded claims on success; raises ``JWTError`` on failure.
    """
    return jwt.decode(
        token,
        public_key_pem,
        algorithms=["RS256"],
        issuer=issuer,
        # Audience verification is left to the publisher plugin, which
        # knows its own pub_mbr_id and can check claims["aud"] itself.
        options={"verify_aud": False},
    )
