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
import base64
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

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
from jwt_utils import ALS_SIGNING_KID, JWKSCache, sign_session_token, verify_keycloak_id_token, verify_session_token
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
            return _hand_off_token(
                redirect_uri, cached_token, state, publisher.handoff
            )

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

    # PKCE (RFC 7636). Keycloak clients here are configured to require it, and
    # without a challenge the home base refuses the request outright with
    # "Missing parameter: code_challenge_method" -- which bounces the reader
    # to the callback with no code and ends the journey before it starts.
    #
    # It is also correct on the merits: the verifier never leaves this service,
    # so an intercepted authorization code cannot be redeemed by anyone else.
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")
    session["code_verifier"] = verifier

    params = {
        "client_id": client_id,
        "redirect_uri": f"{settings.als_base_url}/auth/callback",
        "response_type": "code",
        "scope": scope,
        "state": _encode_state(session_key),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
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
    named_publisher: dict[str, Any] | None = None,
) -> HTMLResponse:
    """
    Ask the visitor which home base is theirs (demo script steps 20, 24).

    This screen is the network explaining itself to someone who has never heard
    of it, at the least convenient possible moment -- mid-article, wanting to
    read. Its first job is therefore to say what a home base *is*, because the
    word means nothing on first encounter and the obvious guess is wrong: the
    natural thing to type is the newspaper you are reading, which is exactly
    what it is not.

    An earlier version asked "Where do you have an account?" over a bare list of
    two names. A reader typed the publisher's name, was shown two unexplained
    options, and had no way to choose. Everything here follows from that: the
    analogy up front, each home base described rather than merely named, and a
    specific answer when someone names a publisher instead.

    All interpolated values are escaped: names come from the ITEGA registry and
    the message may echo what the visitor typed.
    """
    signed_state = html.escape(_encode_state(session_key))

    def link(hb: dict[str, Any]) -> str:
        q = html.escape(urllib.parse.quote(hb["publishing_member_id"]))
        return f'/auth/select-home-base?state={signed_state}&amp;q={q}'

    cards = "".join(
        f'''<a class="hb" href="{link(hb)}">
             <span class="hb-name">{html.escape(hb["name"])}</span>
             <span class="hb-id">{html.escape(hb.get("publishing_member_id", ""))}</span>
           </a>'''
        for hb in candidates
    )

    # Someone typed a newspaper's name. Say so plainly, and say what to do.
    if named_publisher:
        message = (
            f'''\u201c{named_publisher.get("name", "")}\u201d is a newspaper in the '''
            "network, not a home base. Your home base is the organisation that "
            "keeps your account and pays for what you read \u2014 often a different "
            "paper, a library, or an internet provider."
        )

    note = f'<p class="note">{html.escape(message)}</p>' if message else ""

    signup = ""
    if default_signup:
        signup = (
            '<div class="newhere"><h2>I don\u2019t have one</h2>'
            "<p>Then you are new here, which is fine. A home base is free to "
            "join and takes a moment.</p>"
            f'<a class="btn" href="{html.escape(default_signup.get("signup_url", ""))}">'
            f'Create an account with {html.escape(default_signup["name"])}</a></div>'
        )

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Which home base is yours?</title>
  <style>
    :root {{
      --ink:#15222b; --soft:#55676f; --rule:#d3dcd8; --paper:#f3f5f3;
      --card:#fff; --accent:#2a5c6b; --warm:#8a6a12;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --ink:#e7ece9; --soft:#a3b3ba; --rule:#33454d; --paper:#141d23;
               --card:#1a262d; --accent:#7fc0d0; --warm:#d3a63c; }}
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:17px/1.6
      -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
      padding:2.5rem 1.25rem 4rem; }}
    .wrap {{ max-width:40rem; margin:0 auto; }}
    h1 {{ font:600 1.9rem/1.2 Georgia,"Times New Roman",serif; margin:0 0 .3em; }}
    h2 {{ font:600 1.15rem/1.3 Georgia,serif; margin:0 0 .4em; }}
    .lede {{ color:var(--soft); margin:0 0 1.4rem; }}
    .analogy {{ background:var(--card); border:1px solid var(--rule);
      border-left:3px solid var(--accent); padding:1rem 1.15rem; margin:0 0 1.6rem;
      font-size:.98rem; color:var(--soft); }}
    .analogy b {{ color:var(--ink); }}
    .note {{ background:var(--card); border:1px solid var(--rule);
      border-left:3px solid var(--warm); padding:.85rem 1rem; margin:0 0 1.4rem;
      font-size:.98rem; }}
    .hb {{ display:flex; justify-content:space-between; align-items:baseline;
      gap:1rem; background:var(--card); border:1px solid var(--rule);
      border-left:3px solid var(--accent); padding:.95rem 1.1rem; margin-bottom:.6rem;
      text-decoration:none; color:inherit; }}
    .hb:hover, .hb:focus-visible {{ border-left-width:6px; padding-left:.85rem; }}
    .hb:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
    .hb-name {{ font-weight:600; }}
    .hb-id {{ font:.82rem ui-monospace,Menlo,monospace; color:var(--soft); }}
    form {{ margin:1.6rem 0 0; }}
    label {{ display:block; font-size:.95rem; color:var(--soft); margin-bottom:.35rem; }}
    input[type=text] {{ width:100%; padding:.65rem .8rem; font-size:1rem;
      border:1px solid var(--rule); background:var(--card); color:var(--ink); }}
    input[type=text]:focus-visible {{ outline:2px solid var(--accent); outline-offset:1px; }}
    .btn {{ display:inline-block; margin-top:.7rem; padding:.6rem 1.1rem;
      font-size:1rem; background:var(--accent); color:var(--paper);
      border:0; text-decoration:none; cursor:pointer; }}
    .newhere {{ margin-top:2.2rem; padding-top:1.4rem; border-top:1px solid var(--rule); }}
    details {{ margin-top:2rem; font-size:.95rem; color:var(--soft); }}
    summary {{ cursor:pointer; color:var(--accent); }}
    details p {{ margin:.7rem 0 0; }}
  </style>
</head>
<body>
<div class="wrap">
  <h1>Which home base is yours?</h1>
  <p class="lede">You are about to read something from a newspaper you do not
     subscribe to. Rather than asking you to open another account, we can ask
     an organisation you already belong to to vouch for you and settle up.</p>

  <div class="analogy">
    <b>Think of it like a bank card.</b> Your bank issued it; the shop accepts it
    without ever learning your name or your balance. Your <b>home base</b> is the
    bank. The newspaper you are reading is the shop &mdash; so it is not the
    answer to this question.
  </div>

  {note}

  <h2>Sign in through one of these</h2>
  {cards}

  <form method="GET" action="/auth/select-home-base">
    <input type="hidden" name="state" value="{signed_state}">
    <label for="q">Or type its name, or its Publishing Member ID if you know it</label>
    <input type="text" id="q" name="q" autocomplete="off"
           placeholder="e.g. Publisher C Home Base, or ITEGA-PC-0001">
    <button class="btn" type="submit">Continue</button>
  </form>

  {signup}

  <details>
    <summary>What is a home base, exactly?</summary>
    <p>It is the one organisation in this network that knows who you are. It
       holds your account, and when you read something at another member
       publisher it pays them on your behalf and bills you however you have
       agreed &mdash; as part of a subscription, or per article.</p>
    <p>A home base can be a newspaper, but it can equally be a library, a
       university or an internet provider. What matters is that it is the party
       you already have a relationship with.</p>
    <p>The publisher you are reading never learns your name, your email, or
       which other papers you read. It receives only a meaningless identifier,
       and a different one at every publisher, so no two of them can compare
       notes about you.</p>
  </details>
</div>
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

    # Before saying "no match", check whether they named a publisher. It is the
    # most likely wrong answer -- the paper they are reading is the thing in
    # front of them -- and "we could not find that" is a useless reply to it.
    named_publisher = await _discovery.publisher_named(q) if q else None

    if named_publisher:
        message = ""          # the chooser writes a specific one for this case
    elif matches:
        message = "More than one home base matched. Please pick yours."
    else:
        message = (
            f"Nothing in the network matches “{q}”. Pick one below, or if you "
            "do not have a home base yet, create one."
        )
    return _render_home_base_chooser(
        session_key=session_key,
        candidates=matches or await _discovery.home_bases(),
        default_signup=resolved.get("default_signup"),
        message=message,
        named_publisher=named_publisher,
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
    # Prove we are the same party that began the exchange.
    verifier = session.get("code_verifier")
    if verifier:
        token_payload["code_verifier"] = verifier

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

    # 7. Deliver the session token by whichever means this client can read.
    #    SECURITY: never the query string. A POST body keeps the token out of
    #    the URL entirely; a fragment keeps it out of every server log, since
    #    browsers do not transmit fragments. A query parameter would land in
    #    browser history, access logs and Referer headers alike.
    response = _hand_off_token(
        publisher_redirect_uri, session_token, publisher_state, publisher.handoff
    )

    # 8. Remember this reader so the next publisher does not send them back
    #    through login, and record the token we just issued so a return visit
    #    to THIS publisher needs no round trip at all.
    if _session_cache is not None:
        handle = _session_cache.remember(
            request.cookies.get(_SESSION_COOKIE, ""),
            home_base["id"],
            id_token=id_token_raw,
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


def _hand_off_token(
    redirect_uri: str,
    session_token: str,
    publisher_state: str,
    mode: str = "post",
) -> Response:
    """
    Return the session token to whoever asked for it, by the means they can read.

    ``post`` suits anything with a server at the far end: the token travels in a
    form body and never appears in a URL.

    ``fragment`` suits a single-page app, which has no server to receive a POST
    and cannot see the body at all -- the reader simply arrives at a fresh,
    signed-out page, which is precisely the fault this exists to fix. The token
    rides in the URL fragment, which browsers do not transmit and servers
    therefore never log.
    """
    if mode == "fragment":
        params = urllib.parse.urlencode({
            "session_token": session_token,
            "state": publisher_state,
        })
        return RedirectResponse(url=f"{redirect_uri}#{params}", status_code=302)
    return _post_token_to_publisher(redirect_uri, session_token, publisher_state)


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


# ── GET /auth/logout ─────────────────────────────────────────────────
#
# Ending a session in a federated network means choosing how far to go, and
# only the reader can answer that. Signing out of a shared library machine is
# not the same act as signing out of a laptop at home, so the publisher offers
# both and this endpoint carries out whichever was asked for.
#
#   scope=here        Leave this publisher. The reader stays signed in to the
#                     network, so the next publisher still recognises them.
#
#   scope=everywhere  End the network session and the session at the home base
#                     with it. The next visit anywhere begins at the chooser.
#
# "Here" is not merely the publisher's own business. The Authenticator caches
# the token it issued for each publisher, so a reader who logs out of
# WordPress and clicks a gated article is handed that cached token and signed
# straight back in. Dropping it is what makes the publisher's logout real.

@app.get("/auth/logout")
async def logout(
    request: Request,
    scope: str = "here",
    pub_mbr_id: str = "",
    client_id: str = "",
    redirect_uri: str = "",
) -> RedirectResponse:
    """
    End a reader's session, at this publisher or across the network.

    Returns the reader to ``redirect_uri`` when it belongs to the publisher
    identified by ``client_id``, and to the ALS itself otherwise.
    """
    if scope not in ("here", "everywhere"):
        raise HTTPException(
            status_code=400,
            detail="scope must be 'here' or 'everywhere'",
        )

    # Where to send the reader afterwards. An unvalidated redirect_uri here
    # would be an open redirect on an authentication domain -- the most
    # convincing possible place to host one -- so it is checked against the
    # publisher's registered origin exactly as /auth/authorize checks its own.
    return_to = f"{settings.als_base_url}/auth/logged-out"
    publisher = _publishers.get(client_id)
    if publisher is not None and redirect_uri:
        registered = urllib.parse.urlparse(publisher.redirect_uri)
        requested = urllib.parse.urlparse(redirect_uri)
        if (
            registered.scheme == requested.scheme
            and registered.netloc == requested.netloc
        ):
            return_to = redirect_uri
        else:
            logger.warning(
                "logout: redirect_uri rejected — registered=%s, requested=%s",
                publisher.redirect_uri,
                redirect_uri,
            )

    handle = request.cookies.get(_SESSION_COOKIE, "")

    if _session_cache is None or not handle:
        # Nothing cached to end. Still a successful logout from the reader's
        # point of view, so send them on rather than showing them an error.
        return RedirectResponse(url=return_to, status_code=302)

    if scope == "here":
        dropped = _session_cache.forget_token(handle, pub_mbr_id)
        logger.info(
            "logout(here): publisher=%s token_dropped=%s",
            pub_mbr_id or "(unnamed)",
            dropped,
        )
        return RedirectResponse(url=return_to, status_code=302)

    # ── everywhere ───────────────────────────────────────────────────
    # Two sessions have to end, and they are held by different parties: the
    # network session here, and the reader's session at their home base. This
    # service can only end the first directly; the second is ended by sending
    # the reader to the home base's end-session endpoint, which is what
    # OpenID Connect RP-Initiated Logout is for.
    home_base_id = _session_cache.home_base_for(handle) or ""
    id_token = _session_cache.id_token_for(handle)
    _session_cache.forget(handle)

    home_base = await _discovery.get(home_base_id) if _discovery else None

    if home_base is None:
        logger.info("logout(everywhere): network session ended, home base unknown")
        response = RedirectResponse(url=return_to, status_code=302)
        _clear_session_cookie(response)
        return response

    params: dict[str, str] = {"post_logout_redirect_uri": return_to}
    if id_token:
        # Identifies the session to end without asking the reader again.
        params["id_token_hint"] = id_token
    elif client_id:
        # Keycloak accepts client_id in place of a hint, but then shows a
        # confirmation page rather than logging out silently.
        params["client_id"] = client_id

    end_session = (
        f"{home_base['oidc_issuer']}/protocol/openid-connect/logout"
        f"?{urllib.parse.urlencode(params)}"
    )
    logger.info("logout(everywhere): ending session at %s", home_base["id"])

    response = RedirectResponse(url=end_session, status_code=302)
    _clear_session_cookie(response)
    return response


def _clear_session_cookie(response: RedirectResponse) -> None:
    """
    Expire the Authenticator's first-party cookie.

    The attributes must match those it was set with, or the browser keeps the
    original and the reader stays signed in to the network after being told
    they are not.
    """
    response.delete_cookie(
        key=_SESSION_COOKIE,
        httponly=True,
        secure=True,
        samesite="lax",
    )


@app.get("/auth/logged-out", response_class=HTMLResponse)
async def logged_out() -> HTMLResponse:
    """
    Confirm the session has ended.

    Only reached when the publisher sent no usable return address, or when the
    home base returns the reader here after ending its own session.
    """
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8>"
        "<title>Signed out</title>"
        "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:32rem;"
        "margin:18vh auto;padding:0 1.5rem;color:#15222b}"
        "h1{font:600 1.5rem/1.2 Georgia,serif;margin:0 0 .6rem}"
        "p{color:#4a5c66;margin:0}</style>"
        "<h1>You are signed out.</h1>"
        "<p>Your session with the network has ended. Visiting any member "
        "publisher will start a new one.</p>"
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
    jwk["kid"] = ALS_SIGNING_KID   # same constant the signer stamps
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
