"""
ALS Auth Service — FastAPI application.

This service acts as the federation broker between publishers (WordPress OIDC
clients) and home bases (Keycloak identity providers). It issues short-lived
ALS session tokens that carry only opaque, pseudonymous identifiers — the ALS
never sees or stores any PII.

Endpoints
---------
GET  /auth/authorize               — Start OIDC authorization flow
GET  /auth/callback                — Handle Keycloak callback
POST /auth/validate                — Validate an ALS session token
GET  /auth/home-bases              — List certified home bases
GET  /.well-known/openid-configuration — OIDC discovery document
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
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

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

# In-memory session store.  For production this should be replaced with
# Redis or an encrypted cookie; an in-memory dict is sufficient for the
# prototype and avoids external dependencies.
_pending_sessions: dict[str, dict[str, str]] = {}


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

def _make_session_key() -> str:
    """Generate a cryptographically random session key."""
    return secrets.token_urlsafe(32)


def _encode_state(session_key: str) -> str:
    """
    Produce an HMAC-signed state parameter that embeds the session key.

    Format: base64(session_key) . base64(hmac_sha256(session_key))
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
    """Fire-and-forget POST to the ALS Logging Service."""
    url = f"{settings.logging_service_url}/log/event"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
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
    # 1. Validate client_id
    if client_id not in _publishers:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown client_id: {client_id}",
        )
    publisher = _publishers[client_id]

    # 2. Check for home-site hint (cookie or header).  For the prototype
    #    with a single home base we always redirect to Keycloak directly.
    #    A multi-home-base deployment would present a chooser here.
    home_site_hint = (
        request.cookies.get("newshare_home_base")
        or request.headers.get("X-Home-Base-Hint")
    )
    # For now, we ignore the hint and always go to the configured Keycloak.

    # 3. Store session context
    session_key = _make_session_key()
    _pending_sessions[session_key] = {
        "publisher_client_id": client_id,
        "publisher_redirect_uri": redirect_uri,
        "publisher_state": state,
        "scope": scope,
    }

    # 4. Build Keycloak authorization URL
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
    # 5. Redirect user to Keycloak
    return RedirectResponse(url=keycloak_url, status_code=302)


# ── GET /auth/callback ───────────────────────────────────────────────

@app.get("/auth/callback")
async def callback(
    code: str = Query(..., description="Authorization code from Keycloak"),
    state: str = Query(..., description="HMAC-signed state round-tripped through Keycloak"),
    session_state: str = Query("", description="Keycloak session state (informational)"),
) -> RedirectResponse:
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

    # 4. Extract custom claims
    network_user_id = id_claims.get("networkUserId", id_claims.get("sub", ""))
    home_base_id = id_claims.get("homeBaseId", "")
    network_group_id = id_claims.get("networkGroupId", 0)
    pub_mbr_id = id_claims.get("pubMbrId", publisher.pub_mbr_id)

    if not network_user_id:
        raise HTTPException(status_code=502, detail="Missing networkUserId in ID token")

    # 5. Issue ALS session token
    now = int(time.time())
    session_id = f"sess-{secrets.token_hex(8)}"

    als_claims = {
        "iss": settings.als_base_url,
        "sub": network_user_id,
        "aud": pub_mbr_id,
        "exp": now + settings.session_token_ttl,
        "iat": now,
        "networkUserId": network_user_id,
        "homeBaseId": home_base_id,
        "networkGroupId": network_group_id,
        "pubMbrId": pub_mbr_id,
        "sessionId": session_id,
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

    # 7. Redirect back to the publisher
    separator = "&" if "?" in publisher_redirect_uri else "?"
    redirect_url = (
        f"{publisher_redirect_uri}{separator}"
        f"session_token={urllib.parse.quote(session_token, safe='')}"
        f"&state={urllib.parse.quote(publisher_state, safe='')}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


# ── POST /auth/validate ──────────────────────────────────────────────

@app.post(
    "/auth/validate",
    response_model=TokenValidationResponse,
    responses={401: {"model": ErrorResponse}},
)
async def validate_token(body: TokenValidationRequest) -> TokenValidationResponse:
    """
    Validate an ALS-issued session token.

    Returns the decoded claims if the token is valid, or 401 if not.
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
    """
    base = settings.als_base_url
    return OIDCDiscovery(
        issuer=base,
        authorization_endpoint=f"{base}/auth/authorize",
        token_endpoint=f"{base}/auth/callback",
        jwks_uri=f"{base}/.well-known/jwks.json",
        response_types_supported=["code"],
        subject_types_supported=["pairwise"],
        id_token_signing_alg_values_supported=["RS256"],
    )


# ── GET /.well-known/jwks.json ────────────────────────────────────────

@app.get("/.well-known/jwks.json")
async def jwks_endpoint() -> dict[str, Any]:
    """
    Expose the ALS public key in JWKS format so that publishers can
    verify ALS-issued session tokens without a shared secret.
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
