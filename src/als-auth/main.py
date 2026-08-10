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
import html
import json
import logging
import secrets
import time
import urllib.parse
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import OrderedDict
from typing import Any

import httpx
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ai_agent_models import (
    AgentVerifyRequest,
    AgentVerifyResponse,
    BusinessRules,
    GrantCheckRequest,
    GrantCheckResponse,
    GrantRequest,
    GrantResponse,
)
from ai_agents import AIAgentRegistry
from config import Settings, settings
from discovery import DiscoveryClient
from session_cache import AuthenticatorSessionCache
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

# ── CORS ─────────────────────────────────────────────────────────────
#
# The demonstration dashboard calls this service directly from a browser, and
# in production it is served from a different host, so those requests are
# cross-origin. Origins are listed explicitly rather than wildcarded: these
# endpoints answer questions about network membership and pricing, and there
# is no reason for arbitrary sites to be able to ask them from a visitor's
# browser.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── State holders (populated on startup) ──────────────────────────────

_discovery: DiscoveryClient | None = None
# One JWKS cache per home base, keyed by ITEGA home base id.  Each home base
# signs its own ID tokens, so the ALS must verify against that home base's
# keys -- never a single shared key set.
_jwks_caches: dict[str, JWKSCache] = {}
_publishers: dict[str, Any] = {}          # client_id -> PublisherEntry
_private_key_pem: str = ""
_public_key_pem: str = ""

# Readers already authenticated at the Authenticator. Consulted before any
# home-base discovery happens, per the step preceding script step 10.
_session_cache: AuthenticatorSessionCache | None = None

# Certified AI agents and their crawl grants. Separate from reader sessions:
# an agent acts for a business, identifies itself on every request, and is
# never redirected or asked to log in.
_ai_agents: AIAgentRegistry | None = None

# Name of the first-party cookie holding an opaque handle into that cache.
# It carries no identifiers and is scoped to the Authenticator's own domain.
_SESSION_COOKIE = "itega_session"

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
    global _discovery, _publishers, _private_key_pem, _public_key_pem
    global _session_cache, _ai_agents

    logger.info("Starting ALS Auth Service")

    # Readers stay recognised here for the life of a session token, so a
    # second publisher does not send them back through login.
    _session_cache = AuthenticatorSessionCache(ttl=settings.session_token_ttl)

    # The certified-AI-agent table publishers consult before serving crawlers.
    _ai_agents = AIAgentRegistry(
        registry_path=settings.ai_agents_registry_path,
        default_grant_ttl=settings.ai_grant_ttl,
    )

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

    # Connect to Network Discovery — the registry of certified home bases.
    _discovery = DiscoveryClient(
        base_url=settings.discovery_service_url,
        ttl=settings.jwks_cache_ttl,
    )
    logger.info("Discovery client initialised (url=%s)", settings.discovery_service_url)


def _jwks_cache_for(home_base: dict[str, Any]) -> JWKSCache:
    """Return (creating on first use) the JWKS cache for one home base."""
    hb_id = home_base["id"]
    if hb_id not in _jwks_caches:
        _jwks_caches[hb_id] = JWKSCache(
            jwks_url=home_base["jwks_uri"],
            ttl=settings.jwks_cache_ttl,
        )
        logger.info("JWKS cache created for %s (%s)", hb_id, home_base["jwks_uri"])
    return _jwks_caches[hb_id]


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

    # 3. Before anything else, look in our own store of readers who have
    #    already authenticated (the step preceding script step 10).  Only
    #    when nothing fresh is found do we fall back to discovery.
    handle = request.cookies.get(_SESSION_COOKIE, "")
    if _session_cache is not None and handle:
        cached_token = _session_cache.token_for(handle, publisher.pub_mbr_id)
        if cached_token is not None:
            # This reader already holds a valid token for THIS publisher, so
            # the pairwise identifier inside it is the right one.  Hand it
            # straight back; no home base round trip at all.
            logger.info(
                "authorize: served %s from Authenticator cache",
                publisher.pub_mbr_id,
            )
            return _post_token_to_publisher(redirect_uri, cached_token, state)

    # 4. Store session context in the bounded in-memory store.  The chosen
    #    home base is filled in below, or by /auth/select-home-base once the
    #    visitor identifies theirs.
    session_key = _make_session_key()
    _session_store_put(session_key, {
        "publisher_client_id": client_id,
        "publisher_redirect_uri": redirect_uri,
        "publisher_state": state,
        "scope": scope,
        "home_base_id": "",
    })

    # 5. Determine which home base to send the visitor to.
    if _discovery is None:
        raise HTTPException(status_code=503, detail="Discovery client not initialised")

    # A reader we already recognise goes straight back to the home base they
    # use.  We still make the round trip, because only the home base can mint
    # this publisher's pairwise identifier -- but it recognises them and
    # answers without prompting, so nothing is asked of the reader.
    if _session_cache is not None and handle:
        known_id = _session_cache.home_base_for(handle)
        if known_id:
            known = await _discovery.get(known_id)
            if known is not None:
                logger.info(
                    "authorize: known reader -> home base %s, chooser skipped",
                    known_id,
                )
                return await _redirect_to_home_base(session_key, known, client_id, scope)

    # Otherwise fall back to discovery.  The X-Home-Base-Hint header carries a
    # prior affiliation when the publisher knows one; an unhinted visitor is
    # asked directly (demo script Path Option 2, step 20).
    hint = request.headers.get("X-Home-Base-Hint", "")
    client_ip = request.client.host if request.client else ""
    resolved = await _discovery.resolve(q=hint, client_ip=client_ip)

    if resolved.get("exact") and resolved.get("matches"):
        home_base = resolved["matches"][0]
        return await _redirect_to_home_base(session_key, home_base, client_id, scope)

    # 6. No confident match — present the home-base chooser.
    return _render_home_base_chooser(
        session_key=session_key,
        candidates=resolved.get("matches") or await _discovery.home_bases(),
        default_signup=resolved.get("default_signup"),
    )


async def _redirect_to_home_base(
    session_key: str,
    home_base: dict[str, Any],
    client_id: str,
    scope: str,
) -> RedirectResponse:
    """
    Send the visitor to their home base to authenticate.

    The ALS puts *its own* callback in redirect_uri rather than the
    publisher's, so the authorization code comes back here to be exchanged —
    the publisher never talks to the home base directly.
    """
    session = _pending_sessions.get(session_key)
    if session is None:
        raise HTTPException(status_code=400, detail="Session expired or unknown")
    session["home_base_id"] = home_base["id"]

    params = {
        "client_id": client_id,
        "redirect_uri": f"{settings.als_base_url}/auth/callback",
        "response_type": "code",
        "scope": scope,
        "state": _encode_state(session_key),
    }
    auth_url = f"{home_base['auth_url']}?{urllib.parse.urlencode(params)}"

    logger.info(
        "authorize: client_id=%s -> home base %s",
        client_id,
        home_base["id"],
    )
    return RedirectResponse(url=auth_url, status_code=302)


def _render_home_base_chooser(
    session_key: str,
    candidates: list[dict[str, Any]],
    default_signup: dict[str, Any] | None,
    message: str = "",
) -> HTMLResponse:
    """
    Ask the visitor which home base is theirs (demo script steps 20, 24).

    Offers the certified members we can suggest, a free-text field for a name
    or Publishing Member ID, and — when nothing matched — an invitation to
    sign up with a default home base rather than a dead end.

    All interpolated values are HTML-escaped: candidate names come from the
    ITEGA registry and the message may echo visitor input.
    """
    signed_state = html.escape(_encode_state(session_key))

    options = "".join(
        f'<li><a href="/auth/select-home-base?state={signed_state}'
        f'&amp;q={html.escape(urllib.parse.quote(hb["publishing_member_id"]))}">'
        f'{html.escape(hb["name"])}</a></li>'
        for hb in candidates
    )
    note = f"<p class=\"note\">{html.escape(message)}</p>" if message else ""

    signup = ""
    if default_signup:
        signup = (
            '<p class="signup">Not affiliated with a member yet? '
            f'<a href="{html.escape(default_signup.get("signup_url", ""))}">'
            f'Create an account with {html.escape(default_signup["name"])}</a>.</p>'
        )

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Choose your home base</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 34rem; margin: 3rem auto;
           padding: 0 1rem; line-height: 1.5; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin: .35rem 0; }}
    .note {{ background: #fff6e5; border-left: 3px solid #e8a33d; padding: .6rem .8rem; }}
    .signup {{ color: #555; font-size: .95rem; }}
    input[type=text] {{ width: 100%; padding: .5rem; font-size: 1rem; }}
    button {{ margin-top: .6rem; padding: .5rem 1rem; font-size: 1rem; }}
  </style>
</head>
<body>
  <h1>Where do you have an account?</h1>
  <p>Sign in through the publisher or service that maintains your account —
     your <strong>home base</strong>. It is the only party that knows who you are.</p>
  {note}
  <ul>{options}</ul>
  <form method="GET" action="/auth/select-home-base">
    <input type="hidden" name="state" value="{signed_state}">
    <label for="q">Or enter its name or Publishing Member ID</label>
    <input type="text" id="q" name="q" autocomplete="off">
    <button type="submit">Continue</button>
  </form>
  {signup}
</body>
</html>
""")


# ── GET /auth/select-home-base ───────────────────────────────────────

@app.get("/auth/select-home-base")
async def select_home_base(
    request: Request,
    state: str = Query(..., description="Signed state from the chooser"),
    q: str = Query("", description="Home base name or Publishing Member ID"),
):
    """
    Handle the visitor's answer to the home-base chooser (script steps 20-24).

    On a confident match, redirect onward to that home base to authenticate.
    Otherwise re-present the chooser with whatever candidates were found, or
    an invitation to sign up if nothing matched at all.
    """
    if _discovery is None:
        raise HTTPException(status_code=503, detail="Discovery client not initialised")

    try:
        session_key = _decode_state(state)
    except ValueError as exc:
        logger.warning("select-home-base: invalid state — %s", exc)
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    session = _pending_sessions.get(session_key)
    if session is None:
        raise HTTPException(status_code=400, detail="Session expired or unknown")

    client_ip = request.client.host if request.client else ""
    resolved = await _discovery.resolve(q=q, client_ip=client_ip)
    matches = resolved.get("matches") or []

    if resolved.get("exact") and matches:
        return await _redirect_to_home_base(
            session_key,
            matches[0],
            session["publisher_client_id"],
            session["scope"],
        )

    if matches:
        message = "More than one home base matched — please pick yours."
    else:
        message = (
            f"We could not find a home base matching “{q}”. "
            "Choose from the list, or create an account below."
        )
    return _render_home_base_chooser(
        session_key=session_key,
        candidates=matches or await _discovery.home_bases(),
        default_signup=resolved.get("default_signup"),
        message=message,
    )


# ── GET /auth/callback ───────────────────────────────────────────────

@app.get("/auth/callback")
async def callback(
    request: Request,
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

    # 2. Recover the home base this session authenticated against.  Every
    #    home base has its own token endpoint, issuer, and signing keys, so
    #    the rest of this handler is scoped to that one member.
    if _discovery is None:
        raise HTTPException(status_code=503, detail="Discovery client not initialised")

    home_base = await _discovery.get(session.get("home_base_id", ""))
    if home_base is None:
        logger.warning(
            "callback: session referenced unknown home base %s",
            session.get("home_base_id"),
        )
        raise HTTPException(status_code=400, detail="Unknown home base for this session")

    # 3. Exchange authorization code with the home base
    als_callback_uri = f"{settings.als_base_url}/auth/callback"
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": als_callback_uri,
        "client_id": publisher_client_id,
        "client_secret": publisher.client_secret,
    }

    token_url = f"{home_base['oidc_issuer']}/protocol/openid-connect/token"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(token_url, data=token_payload)
            resp.raise_for_status()
            token_data = resp.json()
    except httpx.HTTPError as exc:
        logger.error("Token exchange with %s failed: %s", home_base["id"], exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to exchange authorization code with home base",
        )

    id_token_raw = token_data.get("id_token")
    if not id_token_raw:
        raise HTTPException(status_code=502, detail="No id_token in home base response")

    # 4. Validate the ID token against that home base's published keys
    try:
        id_claims = await verify_keycloak_id_token(
            token=id_token_raw,
            jwks_cache=_jwks_cache_for(home_base),
            issuer=home_base["oidc_issuer"],
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
    # Fall back to the home base we actually authenticated against, so the
    # claim is correct even before a home base deploys the Keycloak mapper.
    home_base_id = id_claims.get("homeBaseId") or home_base["id"]
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
            # The ALS files authentication events itself. They carry no price
            # and are excluded from settlement, but the filer is recorded for
            # consistency with the content-access records.
            "reporter": "als",
        }
    )

    # 7. Deliver the session token to the publisher via an auto-submitting
    #    HTML form.  SECURITY: The token is sent in the POST body, NOT in
    #    the URL query string.  Putting secrets in the URL would expose them
    #    in browser history, server access logs, and Referer headers.
    response = _post_token_to_publisher(
        publisher_redirect_uri, session_token, publisher_state
    )

    # 8. Remember this reader so the next publisher does not send them back
    #    through login, and record the token we just issued so a return visit
    #    to THIS publisher needs no round trip at all.
    if _session_cache is not None:
        handle = _session_cache.remember(
            request.cookies.get(_SESSION_COOKIE, ""), home_base["id"]
        )
        _session_cache.store_token(
            handle, pub_mbr_id, session_token, now + settings.session_token_ttl
        )
        # First-party, on the Authenticator's own domain, holding nothing but
        # an opaque handle.  HttpOnly so page scripts cannot read it; SameSite
        # Lax so it survives the top-level redirect back from the home base
        # but is not sent on cross-site subrequests.
        response.set_cookie(
            key=_SESSION_COOKIE,
            value=handle,
            max_age=settings.session_token_ttl,
            httponly=True,
            secure=True,
            samesite="lax",
        )

    return response


def _post_token_to_publisher(
    redirect_uri: str,
    session_token: str,
    publisher_state: str,
) -> HTMLResponse:
    """
    Hand a session token to the publisher via an auto-submitting form.

    The token travels in a POST body rather than the URL, keeping it out of
    browser history, server access logs, and Referer headers.

    All three interpolated values are HTML-escaped before being placed in
    attributes.  ``publisher_state`` is echoed back from the publisher's
    original query string, so without escaping a crafted state could close the
    attribute and inject markup into this page.
    """
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html><body>
<form id="f" method="POST" action="{html.escape(redirect_uri, quote=True)}">
  <input type="hidden" name="sessionToken" value="{html.escape(session_token, quote=True)}">
  <input type="hidden" name="state" value="{html.escape(publisher_state, quote=True)}">
</form>
<script>document.getElementById('f').submit();</script>
</body></html>
""")


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

    Sourced from ITEGA's Network Discovery Service, which is the authority
    on who is currently certified — a suspended member disappears from this
    list without the ALS being redeployed.
    """
    if _discovery is None:
        raise HTTPException(status_code=503, detail="Discovery client not initialised")

    return HomeBasesResponse(home_bases=[
        HomeBaseEntry(id=hb["id"], name=hb["name"], auth_url=hb["auth_url"])
        for hb in await _discovery.home_bases()
    ])


# ── GET /.well-known/openid-configuration ─────────────────────────────

# ── AI agent handshake ───────────────────────────────────────────────
#
# The machine-to-machine path. An AI answer engine does not use a browser and
# cannot be redirected, so none of the OIDC flow above applies to it: it
# identifies itself on every request, agrees a price, and crawls under a grant
# until that grant times out.
#
# These endpoints are called by the publisher's ITEGA client code, never by the
# agent itself. The agent talks only to the publisher.


@app.post("/ai-agent/verify", response_model=AgentVerifyResponse)
async def verify_ai_agent(body: AgentVerifyRequest) -> AgentVerifyResponse:
    """
    Is this crawler an ITEGA member in good standing? (script steps 3-5)

    Returns the business rules the agent has agreed to, so the publisher can
    check its asking price against them before quoting. A non-member gets a
    refusal carrying somewhere to go — the script is specific that the rejection
    should direct the caller to membership rather than simply closing the door.
    """
    if _ai_agents is None:
        raise HTTPException(status_code=503, detail="Agent registry not initialised")

    agent = _ai_agents.verify(body.agentMbrId, body.apiKey)
    if agent is None:
        return AgentVerifyResponse(
            member=False,
            signupUrl=settings.ai_agent_signup_url,
            reason=(
                "Not a current ITEGA member. Content is available to member "
                "agents under agreed terms; membership is open."
            ),
        )

    rules = agent.get("business_rules", {})
    return AgentVerifyResponse(
        member=True,
        agentMbrId=agent["agentMbrId"],
        name=agent.get("name", ""),
        businessRules=BusinessRules(**rules),
    )


@app.post("/ai-agent/grant", response_model=GrantResponse)
async def issue_ai_grant(body: GrantRequest) -> GrantResponse:
    """
    Record that an agent accepted a publisher's price (script steps 7-9).

    The grant lets the agent keep crawling this publisher without repeating the
    handshake, which matters at crawl volume. It does not suspend accounting:
    every fulfilled request is still logged and billed on its own.
    """
    if _ai_agents is None:
        raise HTTPException(status_code=503, detail="Agent registry not initialised")

    agent = _ai_agents.verify(body.agentMbrId, body.apiKey)
    if agent is None:
        raise HTTPException(status_code=403, detail="Not a current ITEGA member")

    rules = agent.get("business_rules", {})

    # Refuse to grant above what this agent agreed to as a member. The publisher
    # sets its own price, but ITEGA will not record an agreement that breaches
    # the terms of membership.
    ceiling = float(rules.get("maxPricePerResource", 0.0))
    if ceiling and body.agreedPrice > ceiling:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Agreed price {body.agreedPrice} exceeds this agent's "
                f"contracted maximum of {ceiling}"
            ),
        )

    token, expires_at = _ai_agents.issue_grant(
        agent_mbr_id=body.agentMbrId,
        pub_mbr_id=body.pubMbrId,
        agreed_price=body.agreedPrice,
        ttl=int(rules.get("grantTtlSeconds") or settings.ai_grant_ttl),
    )
    return GrantResponse(
        grant=token, expiresAt=expires_at, agreedPrice=body.agreedPrice
    )


@app.post("/ai-agent/grant/check", response_model=GrantCheckResponse)
async def check_ai_grant(body: GrantCheckRequest) -> GrantCheckResponse:
    """
    Is this grant still good for this publisher? (steps 10, 13)

    An invalid answer sends the agent back through the full membership check,
    which is what the timeout is for.
    """
    if _ai_agents is None:
        raise HTTPException(status_code=503, detail="Agent registry not initialised")

    grant = _ai_agents.check_grant(body.grant, body.pubMbrId)
    if grant is None:
        return GrantCheckResponse(valid=False)

    return GrantCheckResponse(
        valid=True,
        agentMbrId=grant["agent_mbr_id"],
        agreedPrice=grant["agreed_price"],
        expiresAt=grant["expires_at"],
    )


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
