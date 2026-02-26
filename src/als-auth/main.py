"""
ALS Auth Service — FastAPI application.

This service acts as the **federation broker** in the Newshare four-party model,
sitting between publishers (WordPress OIDC clients) and home bases (Keycloak
identity providers).  It issues short-lived ALS session tokens that carry only
opaque, pairwise pseudonymous identifiers (PPIDs) — the ALS never sees, stores,
or transmits any PII.

Security invariants
-------------------
- **No cookies.**  Auth state is carried exclusively via HTTP headers and signed
  JWT tokens (per the Newshare spec).
- **PPID isolation.**  Each user gets a different opaque ``sub`` at each
  publisher; cross-site correlation is architecturally impossible without home
  base cooperation.
- **Session tokens in POST bodies.**  Tokens are delivered to publishers via
  auto-submitting HTML forms, never in URL query strings (avoids exposure in
  browser history, server logs, and Referer headers).

Endpoints
---------
GET  /auth/authorize                    — Start OIDC authorization flow
GET  /auth/callback                     — Handle Keycloak callback, issue session token
POST /auth/validate                     — Validate an ALS session token
GET  /auth/home-bases                   — List certified home bases
GET  /.well-known/openid-configuration  — OIDC discovery document
GET  /.well-known/jwks.json             — ALS public key in JWKS format
GET  /healthz                           — Health check
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import OrderedDict
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import Settings, settings
from jwt_utils import JWKSCache, sign_session_token, verify_keycloak_id_token, verify_session_token
from jose import JWTError
from models import (
    ErrorResponse,
    HomeBaseEntry,
    HomeBasesResponse,
    OIDCDiscovery,
    TokenClaims,
    TokenValidationRequest,
    TokenValidationResponse,
)

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("als-auth")

# ── Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="ALS Auth Service",
    version="0.1.0",
    description="Newshare Network ALS — Authentication & Token Issuance",
)

# ── State holders (populated on startup) ──────────────────────────────

_jwks_cache: JWKSCache | None = None
_publishers: dict[str, Any] = {}          # client_id -> PublisherEntry
_private_key_pem: str = ""
_public_key_pem: str = ""

# ── Bounded in-memory session store ───────────────────────────────
#
# Stores pending OIDC authorization sessions between the /auth/authorize
# redirect and the /auth/callback return.  For production this should be
# replaced with Redis or an encrypted cookie; an in-memory OrderedDict is
# sufficient for the prototype and avoids external dependencies.
#
# SECURITY: The store is bounded to _MAX_PENDING_SESSIONS entries to
# prevent memory exhaustion (DoS).  When the limit is reached, the oldest
# entries are evicted.  Additionally, a TTL-based cleanup runs on every
# insertion to remove stale sessions older than _SESSION_TTL seconds.

_MAX_PENDING_SESSIONS = 10_000
_SESSION_TTL = 600  # seconds (10 minutes — generous for an OIDC round-trip)

_pending_sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()


def _session_store_put(key: str, value: dict[str, Any]) -> None:
    """
    Insert a pending session into the bounded store.

    Performs two housekeeping steps on every write:
      1. Evicts entries older than _SESSION_TTL.
      2. If the store is still at capacity, evicts the oldest entry (FIFO).
    """
    now = time.time()

    # --- TTL-based cleanup: walk from oldest and remove expired entries ---
    expired_keys = [
        k for k, v in _pending_sessions.items()
        if now - v.get("_created_at", 0) > _SESSION_TTL
    ]
    for k in expired_keys:
        _pending_sessions.pop(k, None)

    # --- Capacity-based eviction: drop oldest if still at the limit ---
    while len(_pending_sessions) >= _MAX_PENDING_SESSIONS:
        evicted_key, _ = _pending_sessions.popitem(last=False)
        logger.warning("Session store full — evicted oldest session %s", evicted_key[:12])

    value["_created_at"] = now
    _pending_sessions[key] = value


# ── Startup / Shutdown ────────────────────────────────────────────────

@app.on_event("startup")
async def _startup() -> None:
    global _jwks_cache, _publishers, _private_key_pem, _public_key_pem

    logger.info("Starting ALS Auth Service")

    # Load RSA key pair
    try:
        _private_key_pem = settings.read_private_key()
        _public_key_pem = settings.read_public_key()
        logger.info("Loaded ALS RSA key pair")
    except FileNotFoundError:
        logger.warning(
            "ALS RSA key files not found — token signing/validation will fail "
            "until keys are provisioned at %s / %s",
            settings.als_jwt_private_key_path,
            settings.als_jwt_public_key_path,
        )

    # Load publisher registry
    try:
        publishers_list = settings.load_publishers()
        _publishers = {p.client_id: p for p in publishers_list}
        logger.info("Loaded %d publisher(s) from config", len(_publishers))
    except Exception:
        logger.exception("Failed to load publishers config")

    # Initialise JWKS cache (first fetch is deferred to first use)
    _jwks_cache = JWKSCache(
        jwks_url=settings.keycloak_jwks_url,
        ttl=settings.jwks_cache_ttl,
    )
    logger.info("JWKS cache initialised (url=%s)", settings.keycloak_jwks_url)


# ── Helpers ───────────────────────────────────────────────────────────
#
# These utilities manage the OIDC ``state`` parameter that round-trips
# through Keycloak.  The state embeds a session key (used to look up the
# pending session context) and an HMAC signature (to detect tampering).
# On callback, _decode_state verifies the HMAC using constant-time
# comparison (hmac.compare_digest) before looking up the session.

def _make_session_key() -> str:
    """Generate a cryptographically random session key (256 bits)."""
    return secrets.token_urlsafe(32)


def _encode_state(session_key: str) -> str:
    """
    Produce an HMAC-signed state parameter that embeds the session key.

    Format: base64url(session_key) . base64url(hmac-sha256(session_key))

    The HMAC is keyed with ``settings.session_secret`` so that only this
    ALS instance can produce or verify valid state values.
    """
    key_b64 = urlsafe_b64encode(session_key.encode()).decode()
    sig = hmac.new(
        settings.session_secret.encode(),
        session_key.encode(),
        hashlib.sha256,
    ).digest()
    sig_b64 = urlsafe_b64encode(sig).decode()
    return f"{key_b64}.{sig_b64}"


def _decode_state(state: str) -> str:
    """
    Verify and extract the session key from the signed state parameter.

    Raises ValueError if the HMAC is invalid.
    """
    try:
        key_b64, sig_b64 = state.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed state parameter") from exc

    session_key = urlsafe_b64decode(key_b64).decode()
    expected_sig = hmac.new(
        settings.session_secret.encode(),
        session_key.encode(),
        hashlib.sha256,
    ).digest()
    actual_sig = urlsafe_b64decode(sig_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("State HMAC verification failed")
    return session_key


async def _log_event(payload: dict[str, Any]) -> None:
    """
    Fire-and-forget POST to the ALS Logging Service.

    CRITICAL: The logging service requires an ``X-API-Key`` header
    (enforced by its ``verify_api_key`` dependency).  Without this header
    every event-log request would be rejected with HTTP 403.
    """
    url = f"{settings.logging_service_url}/log/event"
    # Authenticate with the logging service using the shared API key.
    headers = {"X-API-Key": settings.logging_api_key}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code not in (200, 201, 202):
                logger.warning(
                    "Logging service returned %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
    except httpx.HTTPError as exc:
        logger.warning("Failed to reach logging service: %s", exc)


# ── Health ────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ── GET /auth/authorize ──────────────────────────────────────────────

@app.get("/auth/authorize")
async def authorize(
    request: Request,
    client_id: str = Query(..., description="Publisher's registered client_id"),
    redirect_uri: str = Query(..., description="Publisher's callback URL"),
    response_type: str = Query("code"),
    scope: str = Query("openid"),
    state: str = Query("", description="Opaque state from the publisher"),
) -> RedirectResponse:
    """
    Begin the federated OIDC authorization flow.

    The publisher redirects the user here.  The ALS validates the request,
    stores session context, and redirects the user to the home base
    (Keycloak) for authentication.
    """
    # 1. Validate client_id — reject requests from unknown publishers.
    if client_id not in _publishers:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown client_id: {client_id}",
        )
    publisher = _publishers[client_id]

    # 2. Validate redirect_uri against the publisher's registered URI.
    #    This prevents open-redirect attacks where an attacker substitutes
    #    a malicious redirect_uri to steal session tokens.  We check that
    #    the provided URI shares the same scheme+host as the registered one.
    registered_origin = urllib.parse.urlparse(publisher.redirect_uri)
    requested_origin = urllib.parse.urlparse(redirect_uri)
    if (
        registered_origin.scheme != requested_origin.scheme
        or registered_origin.netloc != requested_origin.netloc
    ):
        logger.warning(
            "authorize: redirect_uri rejected — registered=%s, requested=%s",
            publisher.redirect_uri,
            redirect_uri,
        )
        raise HTTPException(
            status_code=400,
            detail="redirect_uri does not match the publisher's registered domain",
        )

    # 3. Check for home-site hint via the X-Home-Base-Hint header.
    #    NOTE: The Newshare architecture forbids cookies (auth state is
    #    carried exclusively via HTTP headers and signed JWT tokens).
    #    In production, home-site discovery uses WebFinger (RFC 7033);
    #    the hint header is a shortcut for the single-home-base prototype.
    home_site_hint = request.headers.get("X-Home-Base-Hint")
    # For now, we ignore the hint and always go to the configured Keycloak.
    # A multi-home-base deployment would present a chooser UI here.

    # 4. Store session context in the bounded in-memory store.
    session_key = _make_session_key()
    _session_store_put(session_key, {
        "publisher_client_id": client_id,
        "publisher_redirect_uri": redirect_uri,
        "publisher_state": state,
        "scope": scope,
    })

    # 5. Build Keycloak authorization URL.
    #    The ALS acts as an intermediary: it redirects the user to the home
    #    base (Keycloak) with the ALS callback as redirect_uri, not the
    #    publisher's.  Keycloak will redirect back to /auth/callback after
    #    the user authenticates.
    als_callback_uri = f"{settings.als_base_url}/auth/callback"
    signed_state = _encode_state(session_key)

    params = {
        "client_id": client_id,
        "redirect_uri": als_callback_uri,
        "response_type": "code",
        "scope": scope,
        "state": signed_state,
    }
    keycloak_url = f"{settings.keycloak_auth_url}?{urllib.parse.urlencode(params)}"

    logger.info(
        "authorize: client_id=%s -> redirecting to Keycloak",
        client_id,
    )
    # 6. Redirect user to Keycloak for authentication.
    return RedirectResponse(url=keycloak_url, status_code=302)


# ── GET /auth/callback ───────────────────────────────────────────────

@app.get("/auth/callback")
async def callback(
    code: str = Query(..., description="Authorization code from Keycloak"),
    state: str = Query(..., description="HMAC-signed state round-tripped through Keycloak"),
    session_state: str = Query("", description="Keycloak session state (informational)"),
) -> HTMLResponse:
    """
    Handle the OIDC callback from Keycloak.

    Exchanges the authorization code for tokens, validates the ID token,
    mints an ALS session token, logs the event, and redirects back to the
    publisher.
    """
    # 1. Recover session context from the signed state
    try:
        session_key = _decode_state(state)
    except ValueError as exc:
        logger.warning("callback: invalid state — %s", exc)
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    session = _pending_sessions.pop(session_key, None)
    if session is None:
        raise HTTPException(status_code=400, detail="Session expired or unknown")

    publisher_client_id = session["publisher_client_id"]
    publisher_redirect_uri = session["publisher_redirect_uri"]
    publisher_state = session["publisher_state"]

    publisher = _publishers.get(publisher_client_id)
    if publisher is None:
        raise HTTPException(status_code=400, detail="Publisher no longer registered")

    # 2. Exchange authorization code with Keycloak
    als_callback_uri = f"{settings.als_base_url}/auth/callback"
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": als_callback_uri,
        "client_id": publisher_client_id,
        "client_secret": publisher.client_secret,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                settings.keycloak_token_url,
                data=token_payload,
            )
            resp.raise_for_status()
            token_data = resp.json()
    except httpx.HTTPError as exc:
        logger.error("Token exchange failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to exchange authorization code with home base",
        )

    id_token_raw = token_data.get("id_token")
    if not id_token_raw:
        raise HTTPException(status_code=502, detail="No id_token in Keycloak response")

    # 3. Validate the ID token
    if _jwks_cache is None:
        raise HTTPException(status_code=503, detail="JWKS cache not initialised")

    try:
        id_claims = await verify_keycloak_id_token(
            token=id_token_raw,
            jwks_cache=_jwks_cache,
            issuer=settings.keycloak_issuer,
            audience=publisher_client_id,
        )
    except JWTError as exc:
        logger.warning("ID-token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid ID token from home base")

    # 4. Extract Newshare-specific custom claims from the Keycloak ID token.
    #    These are added by a Keycloak protocol mapper configured per the
    #    Newshare spec.  ``networkUserId`` is the PPID — a pairwise
    #    pseudonymous identifier unique to this user+publisher pair.
    #    ``networkGroupId`` is a bitmask encoding the user's subscription
    #    tier(s) at the home base.  If the ID token doesn't contain the
    #    custom claims, we fall back to OIDC standard ``sub`` or publisher
    #    defaults.
    network_user_id = id_claims.get("networkUserId", id_claims.get("sub", ""))
    home_base_id = id_claims.get("homeBaseId", "")
    network_group_id = id_claims.get("networkGroupId", 0)
    pub_mbr_id = id_claims.get("pubMbrId", publisher.pub_mbr_id)

    if not network_user_id:
        raise HTTPException(status_code=502, detail="Missing networkUserId in ID token")

    # 5. Issue ALS session token — a short-lived JWT signed with the ALS
    #    private RSA key.  The token contains only opaque network-level
    #    identifiers; no PII ever leaves the home base.
    now = int(time.time())
    session_id = f"sess-{secrets.token_hex(8)}"

    als_claims = {
        "iss": settings.als_base_url,           # ALS is the issuer
        "sub": network_user_id,                 # PPID — pairwise per publisher
        "aud": pub_mbr_id,                      # Audience = this publisher
        "exp": now + settings.session_token_ttl, # Short-lived (default 30 min)
        "iat": now,
        "networkUserId": network_user_id,       # Same as sub (Newshare claim)
        "homeBaseId": home_base_id,             # Which home base authenticated
        "networkGroupId": network_group_id,     # Subscription tier bitmask
        "pubMbrId": pub_mbr_id,                 # Publisher member ID
        "sessionId": session_id,                # Unique session identifier
    }

    try:
        session_token = sign_session_token(als_claims, _private_key_pem)
    except Exception as exc:
        logger.error("Failed to sign session token: %s", exc)
        raise HTTPException(status_code=500, detail="Token signing error")

    logger.info(
        "callback: issued session %s for user %s -> publisher %s",
        session_id,
        network_user_id[:12] + "...",
        pub_mbr_id,
    )

    # 6. Log authentication event (fire-and-forget)
    await _log_event(
        {
            "networkUserId": network_user_id,
            "homeBaseId": home_base_id,
            "pubMbrId": pub_mbr_id,
            "resourceId": "",
            "pageClass": 0.0,
            "serviceClass": 0,
            "markupRatio": 0.0,
            "eventType": "authentication",
            "sessionId": session_id,
        }
    )

    # 7. Deliver the session token to the publisher via an auto-submitting
    #    HTML form.  SECURITY: The token is sent in the POST body, NOT in
    #    the URL query string.  Putting secrets in the URL would expose them
    #    in browser history, server access logs, and Referer headers.
    redirect_uri = publisher_redirect_uri
    html = f"""<!DOCTYPE html>
<html><body>
<form id="f" method="POST" action="{redirect_uri}">
  <input type="hidden" name="sessionToken" value="{session_token}">
  <input type="hidden" name="state" value="{publisher_state}">
</form>
<script>document.getElementById('f').submit();</script>
</body></html>
"""
    return HTMLResponse(content=html)


# ── POST /auth/validate ──────────────────────────────────────────────
#
# Called by the publisher's WordPress plugin on every protected page load.
# The plugin sends the ALS session token (received via the POST callback)
# and this endpoint verifies the signature, expiry, and issuer, then
# returns the decoded claims so the plugin can enforce access control
# based on networkGroupId and pageClass.

@app.post(
    "/auth/validate",
    response_model=TokenValidationResponse,
    responses={401: {"model": ErrorResponse}},
)
async def validate_token(body: TokenValidationRequest) -> TokenValidationResponse:
    """
    Validate an ALS-issued session token.

    Returns the decoded claims if the token is valid, or 401 if not.
    The publisher plugin uses the returned ``networkGroupId`` bitmask to
    decide whether the user's subscription tier grants access to the
    requested ``pageClass``.
    """
    if not _public_key_pem:
        raise HTTPException(status_code=503, detail="Public key not loaded")

    try:
        claims = verify_session_token(
            token=body.token,
            public_key_pem=_public_key_pem,
            issuer=settings.als_base_url,
        )
    except JWTError as exc:
        logger.info("validate: token rejected — %s", exc)
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: {exc}",
        )

    return TokenValidationResponse(
        valid=True,
        claims=TokenClaims(**{
            "iss": claims["iss"],
            "sub": claims["sub"],
            "aud": claims["aud"],
            "exp": claims["exp"],
            "iat": claims["iat"],
            "networkUserId": claims["networkUserId"],
            "homeBaseId": claims["homeBaseId"],
            "networkGroupId": claims["networkGroupId"],
            "pubMbrId": claims["pubMbrId"],
            "sessionId": claims["sessionId"],
        }),
    )


# ── GET /auth/home-bases ─────────────────────────────────────────────
#
# Returns the list of ITEGA-certified home bases.  The User Dashboard
# and publisher plugins can use this to present a home-base chooser UI.
# In the prototype there is only one (Keycloak); in production this
# list would be populated from the ITEGA Network Discovery JSON.

@app.get("/auth/home-bases", response_model=HomeBasesResponse)
async def list_home_bases() -> HomeBasesResponse:
    """
    Return the list of certified home bases in the network.

    For the prototype this is a single Keycloak instance.  In production
    the list would come from the ITEGA network-discovery JSON.
    """
    home_bases = [
        HomeBaseEntry(
            id="HB001",
            name="Newshare Home Base (Keycloak)",
            auth_url=settings.keycloak_auth_url,
        ),
    ]
    return HomeBasesResponse(home_bases=home_bases)


# ── GET /.well-known/openid-configuration ─────────────────────────────

@app.get("/.well-known/openid-configuration", response_model=OIDCDiscovery)
async def openid_configuration() -> OIDCDiscovery:
    """
    Minimal OIDC discovery document for the ALS.

    Publishers and other relying parties can use this to discover ALS
    endpoints programmatically.

    IMPORTANT: The ``token_endpoint`` listed here points to /auth/callback,
    which is NOT a standard OAuth 2.0 token endpoint.  The ALS acts as a
    **federation broker**, not a conventional OIDC Provider.  It does not
    issue tokens in response to a client_credentials or authorization_code
    grant from publishers directly; instead, the callback handler exchanges
    the code with the upstream home base (Keycloak) and then mints an ALS
    session token that is delivered back to the publisher via POST form.
    The endpoint is listed here for OIDC metadata compliance only.
    """
    base = settings.als_base_url
    return OIDCDiscovery(
        issuer=base,
        authorization_endpoint=f"{base}/auth/authorize",
        # NOTE: This is the ALS callback handler, not a standard OAuth token
        # endpoint.  See docstring above for the rationale.
        token_endpoint=f"{base}/auth/callback",
        jwks_uri=f"{base}/.well-known/jwks.json",
        response_types_supported=["code"],
        # The ALS issues pairwise pseudonymous identifiers (PPID) — each
        # user gets a different opaque sub claim at each publisher.
        subject_types_supported=["pairwise"],
        id_token_signing_alg_values_supported=["RS256"],
    )


# ── GET /.well-known/jwks.json ────────────────────────────────────────
#
# Publishes the ALS signing public key so that publishers can verify
# session tokens locally without calling /auth/validate.  This enables
# offline token verification at the WordPress plugin level, reducing
# latency and ALS load.

@app.get("/.well-known/jwks.json")
async def jwks_endpoint() -> dict[str, Any]:
    """
    Expose the ALS public key in JWKS format so that publishers can
    verify ALS-issued session tokens without a shared secret.

    The ``kid`` ("als-signing-key-1") should be incremented when the
    ALS key pair is rotated, so that publishers can distinguish old
    and new keys during the rotation window.
    """
    if not _public_key_pem:
        raise HTTPException(status_code=503, detail="Public key not loaded")

    from jose.backends import RSAKey as _RSAKey

    rsa_key = _RSAKey(key=_public_key_pem, algorithm="RS256")
    jwk = rsa_key.to_dict()
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    jwk["kid"] = "als-signing-key-1"
    return {"keys": [jwk]}


# ── Run with uvicorn when executed directly ───────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
