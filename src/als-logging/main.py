"""
ALS Logging Service — FastAPI application.

Records content-access and authentication events into a TimescaleDB hypertable
and exposes reporting endpoints.  All stored data uses opaque, pseudonymous
identifiers (PPIDs) — no PII is ever stored or returned by this service.

This is component #3 in the Newshare four-party architecture:

    Publisher  -->  ALS Auth  -->  **ALS Logging (this service)**  -->  ALS Settlement

The logging service is the authoritative source of truth for all metered
events in the network.  The settlement batch job reads from this database
to compute financial obligations between home bases and publishers.

Access-control model for reports
--------------------------------
- **Home bases** (IdSPs) receive **full clickstream** data for their own
  users, because they are the identity provider and billing counterpart.
  Endpoint: GET /log/report/home-base/{home_base_id}

- **Publishers** receive only **aggregated** data grouped by home_base_id.
  Individual user identifiers and per-user event rows are NEVER exposed
  to publishers.  This is a critical privacy requirement of the Newshare
  architecture.  Endpoint: GET /log/report/publisher/{pub_mbr_id}

Storage
-------
The ``access_events`` table is created as a TimescaleDB hypertable
(time-series optimised) when the extension is available.  If TimescaleDB
is not installed, it falls back to a plain PostgreSQL table.  TimescaleDB
provides automatic partitioning by timestamp, which is essential for
efficient range queries during settlement and reporting.

Endpoints
---------
POST /log/event                            -- Record an access event
GET  /log/report/home-base/{home_base_id}  -- Full clickstream for a home base
GET  /log/report/publisher/{pub_mbr_id}    -- Aggregated report for a publisher
GET  /log/stats                            -- Basic operational statistics
GET  /healthz                              -- Health check
"""

from __future__ import annotations

import hmac
import json
# Aliased: FastAPI exports its own Path for path parameters, and its import
# below shadows this one. The collision surfaces only when a request is
# served, so the service starts cleanly and /healthz passes while every
# authenticated call returns 500.
from pathlib import Path as FilePath
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
from jose import JWTError, jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from config import settings
from models import (
    AccessEvent,
    EventRecord,
    HomeBaseReport,
    PublisherAggregate,
    PublisherReport,
    StatsResponse,
)

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("als-logging")

# ── Database pool ─────────────────────────────────────────────────────
#
# asyncpg connection pool to PostgreSQL/TimescaleDB.  Initialised during
# application lifespan startup and shared across all request handlers.

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, raising 503 if unavailable."""
    if _pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return _pool


# ── Lifespan ──────────────────────────────────────────────────────────
#
# Application startup: create the asyncpg connection pool, ensure the
# access_events table exists, and attempt to convert it to a TimescaleDB
# hypertable (for automatic time-based partitioning).
# Application shutdown: close the connection pool gracefully.

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    logger.info("Connecting to database…")
    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_min_connections,
            max_size=settings.db_max_connections,
        )
        logger.info("Database pool created")

        # Ensure the hypertable exists (idempotent)
        async with _pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS access_events (
                    timestamp       TIMESTAMPTZ     NOT NULL,
                    network_user_id VARCHAR(128)    NOT NULL,
                    home_base_id    VARCHAR(32)     NOT NULL,
                    pub_mbr_id      VARCHAR(32)     NOT NULL,
                    resource_id     TEXT            NOT NULL DEFAULT '',
                    page_class      NUMERIC(8,4)   NOT NULL DEFAULT 0,
                    service_class   INTEGER         NOT NULL DEFAULT 0,
                    markup_ratio    NUMERIC(4,2)   NOT NULL DEFAULT 1.0,
                    event_type      VARCHAR(32)     NOT NULL,
                    session_id      VARCHAR(128)    NOT NULL DEFAULT '',
                    reporter        VARCHAR(8)      NOT NULL DEFAULT 'cms'
                );
            """)
            # Added after the table shipped, so bring existing deployments
            # forward rather than requiring a manual migration.
            await conn.execute(
                "ALTER TABLE access_events "
                "ADD COLUMN IF NOT EXISTS reporter VARCHAR(8) NOT NULL DEFAULT 'cms';"
            )
            # Attempt to create a TimescaleDB hypertable.  If TimescaleDB
            # is not installed the extension call will fail gracefully.
            try:
                await conn.execute(
                    "SELECT create_hypertable('access_events', 'timestamp', "
                    "if_not_exists => TRUE);"
                )
                logger.info("access_events hypertable ready")
            except asyncpg.UndefinedFunctionError:
                logger.warning(
                    "TimescaleDB extension not available — "
                    "using plain PostgreSQL table"
                )
            except asyncpg.InvalidObjectDefinitionError:
                # Already a hypertable
                pass
    except Exception:
        logger.exception("Failed to connect to database")
        _pool = None

    yield

    if _pool is not None:
        await _pool.close()
        logger.info("Database pool closed")


# ── Application ───────────────────────────────────────────────────────

app = FastAPI(
    title="ALS Logging Service",
    version="0.1.0",
    description="Newshare Network ALS — Event Logging & Reporting",
    lifespan=lifespan,
)


# ── Auth dependency ───────────────────────────────────────────────────
#
# Two kinds of caller present an ``X-API-Key``:
#
#   * The internal key (``api_key``), held by the ALS Auth Service and the
#     settlement scripts. It may write an event for any publisher, because
#     it files authentication events on behalf of all of them.
#
#   * A per-publisher key, issued to one publisher when its plugin was
#     provisioned. It may only write events for its own Publishing Member
#     ID.
#
# The distinction matters because ``pubMbrId`` arrives in the request body.
# With one shared key, anyone holding it could file reads attributed to any
# publisher -- crediting themselves at settlement, or loading a competitor
# with traffic they never had. The key now decides who you are allowed to
# say you are.

INTERNAL = "*"          # sentinel: may act for any publisher


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    Validate the API key and return the Publishing Member ID it authorises.

    Returns the ``INTERNAL`` sentinel for the service's own key, or the
    publisher's member ID for a per-publisher key.

    SECURITY: Uses ``hmac.compare_digest()`` for constant-time comparison
    to prevent timing side-channel attacks that could leak the key length
    or value byte-by-byte.
    """
    supplied = x_api_key.encode()

    if hmac.compare_digest(supplied, settings.api_key.encode()):
        return INTERNAL

    # Compared against every publisher key rather than looked up, so the
    # work done is the same whether the key is known or not.
    matched = ""
    for key, pub_mbr_id in _publisher_keys().items():
        if hmac.compare_digest(supplied, key.encode()):
            matched = pub_mbr_id

    if not matched:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return matched


def _publisher_keys() -> dict[str, str]:
    """API key -> Publishing Member ID, reloaded when the file changes.

    Read from the same store the discovery service writes when it
    provisions a publisher, so a newly-installed plugin can file its first
    event without this service being restarted.
    """
    global _keys_cache, _keys_mtime
    path = FilePath(settings.publisher_keys_path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if mtime != _keys_mtime:
        try:
            raw = json.loads(path.read_text())
            _keys_cache = {
                e["api_key"]: e["pub_mbr_id"]
                for e in raw.get("domains", {}).values()
                if e.get("api_key") and e.get("pub_mbr_id")
            }
            _keys_mtime = mtime
            logger.info("Loaded %d publisher key(s)", len(_keys_cache))
        except Exception:
            logger.exception("Could not read publisher keys from %s", path)
    return _keys_cache


_keys_cache: dict[str, str] = {}
_keys_mtime: float = -1.0


# ── Health ────────────────────────────────────────────────────────────
#
# Unauthenticated health check.  Returns 200 if the database pool is
# connected, 503 otherwise.  Used by load balancers and monitoring.

@app.get("/healthz")
async def healthz() -> dict[str, str]:
    if _pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return {"status": "ok"}


# ── POST /log/event ──────────────────────────────────────────────────
#
# The ALS Auth Service calls this endpoint after every successful
# authentication (event_type="authentication") and the publisher
# WordPress plugin calls it for content access (event_type="content_access").
# The server stamps each event with an authoritative UTC timestamp;
# clients cannot back-date events.

@app.get("/log/whoami")
async def whoami(authorised_for: str = Depends(verify_api_key)) -> dict[str, str]:
    """Which publisher is this key, if any.

    Exists so a publisher can find out that its credentials have stopped
    working. Event filing is deliberately fire-and-forget -- blocking a reader's
    page load on a log write would be indefensible -- which means the plugin
    never sees a rejection. A site whose key was wiped by a database restore or
    revoked by ITEGA goes on serving articles and gating them perfectly while
    filing nothing, and settlement pays it nothing, with no error anywhere a
    person would look.

    So the plugin asks this, on a schedule, where it *can* wait for an answer.
    A 403 here means the key is not one we hold, which is the signal to
    re-certify from scratch. Filing no events and being told so is recoverable;
    filing no events silently is what #50 was about.

    Writes nothing and reads nothing, so asking often costs almost nothing.
    """
    return {
        "pub_mbr_id": "" if authorised_for == INTERNAL else authorised_for,
        "internal": "true" if authorised_for == INTERNAL else "false",
    }


@app.post("/log/event", status_code=202)
async def log_event(
    event: AccessEvent,
    pool: asyncpg.Pool = Depends(_get_pool),
    authorised_for: str = Depends(verify_api_key),
) -> dict[str, str]:
    """
    Record an access event.

    The server adds the authoritative timestamp; the client cannot
    back-date events.  Returns 202 Accepted on success.

    A publisher's key may only file events under its own Publishing Member
    ID. ``pubMbrId`` arrives in the request body, so without this check the
    body decides who gets credited and the key decides nothing.
    """
    if authorised_for != INTERNAL and event.pubMbrId != authorised_for:
        logger.warning(
            "Rejected event: key for %s tried to file as %s",
            authorised_for, event.pubMbrId,
        )
        raise HTTPException(
            status_code=403,
            detail="This key may not file events for that Publishing Member ID",
        )

    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO access_events (
                timestamp, network_user_id, home_base_id, pub_mbr_id,
                resource_id, page_class, service_class, markup_ratio,
                event_type, session_id, reporter
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            now,
            event.networkUserId,
            event.homeBaseId,
            event.pubMbrId,
            event.resourceId,
            event.pageClass,
            event.serviceClass,
            event.markupRatio,
            event.eventType,
            event.sessionId,
            event.reporter,
        )

    logger.info(
        "Logged %s event from %s: user=%s pub=%s",
        event.eventType,
        event.reporter,
        event.networkUserId[:12] + "…",
        event.pubMbrId,
    )
    return {"status": "accepted", "timestamp": now.isoformat()}


# ── GET /log/report/home-base/{home_base_id} ─────────────────────────
#
# Home bases (IdSPs) receive the FULL clickstream for their own users.
# This is permitted because the home base already knows the user's real
# identity (it is the identity provider) and needs per-event detail for
# billing reconciliation and user-facing dashboards.

# ── GET /log/report/me ───────────────────────────────────────────────
#
# A reader's own record, authenticated by the reader's own session token.
#
# The home-base report beside this one needs an API key, because a home base is
# asking about all of its readers. This asks about exactly one, and the only
# party entitled to it is the reader -- who is already holding a signed token
# naming themselves. So the token is the credential, and the identifier is taken
# from inside it rather than from the query string. A reader cannot ask for
# somebody else's history, because there is nowhere to put the request.
#
# This exists because the dashboard was showing invented transactions. Given no
# way to fetch the real ones from a browser, it displayed a fiction instead.

_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched": 0.0}


async def _als_jwks() -> dict[str, Any]:
    """The exchange's public keys, cached briefly."""
    import time as _t
    if _JWKS_CACHE["keys"] and _t.time() - _JWKS_CACHE["fetched"] < 300:
        return _JWKS_CACHE["keys"]
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(f"{settings.als_base_url.rstrip('/')}/.well-known/jwks.json")
        resp.raise_for_status()
        _JWKS_CACHE["keys"] = resp.json()
        _JWKS_CACHE["fetched"] = _t.time()
    return _JWKS_CACHE["keys"]


async def _reader_from_token(authorization: str) -> dict[str, Any]:
    """
    Verify a session token and return its claims.

    Signature checked against the exchange's published keys -- an unverified
    decode here would let anyone read any reader's history by editing a claim.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer session token required")
    token = authorization[7:].strip()
    try:
        return jwt.decode(
            token,
            await _als_jwks(),
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except (JWTError, httpx.HTTPError) as exc:
        logger.warning("rejected a session token: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired session token")


@app.get("/log/report/me")
async def report_me(
    authorization: str = Header("", alias="Authorization"),
    pool: asyncpg.Pool = Depends(_get_pool),
) -> JSONResponse:
    """Everything this reader has read, and what it cost them."""
    claims = await _reader_from_token(authorization)
    network_user_id = claims.get("networkUserId", "")
    if not network_user_id:
        raise HTTPException(status_code=400, detail="Token carries no networkUserId")

    async with pool.acquire() as conn:
        # One purchase is filed twice: by the publisher, and by the reader's
        # own agent. Show the agent's copy where it exists.
        #
        # Not an arbitrary preference. The publisher files markup_ratio = 1.0
        # because it genuinely does not know the reader's markup and is not
        # entitled to -- so its record understates what the reader owes. The
        # agent applied the markup and is the only party that can say what the
        # reader is actually billed.
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (session_id, resource_id)
                   timestamp, pub_mbr_id, resource_id, page_class,
                   markup_ratio, event_type, reporter
              FROM access_events
             WHERE network_user_id = $1
               AND event_type = 'content_access'
               AND page_class > 0
             ORDER BY session_id, resource_id,
                      CASE reporter WHEN 'asp' THEN 0 ELSE 1 END,
                      timestamp DESC
            """,
            network_user_id,
        )
        rows = sorted(rows, key=lambda r: r["timestamp"], reverse=True)[:200]

    # The reader is shown the retail figure, because that is what they owe. The
    # wholesale price is theirs to see too: it is their own agent's margin, and
    # the rule that hides it protects the publisher from learning it, not the
    # reader.
    events = [
        {
            "timestamp": r["timestamp"].isoformat(),
            "pubMbrId": r["pub_mbr_id"],
            "resourceId": r["resource_id"],
            "wholesale": float(r["page_class"]),
            "markupRatio": float(r["markup_ratio"]),
            "retail": round(float(r["page_class"]) * float(r["markup_ratio"]), 4),
            "eventType": r["event_type"],
            "reporter": r["reporter"],
        }
        for r in rows
    ]
    return JSONResponse({
        "networkUserId": network_user_id,
        "homeBaseId": claims.get("homeBaseId", ""),
        "events": events,
        "totalRetail": round(sum(e["retail"] for e in events), 4),
    })


@app.get("/log/report/home-base/{home_base_id}", response_model=HomeBaseReport)
async def report_home_base(
    home_base_id: str = Path(..., max_length=32),
    period_start: datetime = Query(..., description="ISO-8601 start of period"),
    period_end: datetime = Query(..., description="ISO-8601 end of period"),
    pool: asyncpg.Pool = Depends(_get_pool),
    authorised_for: str = Depends(verify_api_key),
) -> HomeBaseReport:
    """
    Full clickstream for a home base's users during the specified period.

    This includes every individual event, because the home base has a
    legitimate operational need to see its own users' activity (they are
    the identity provider and billing counterpart).
    """
    # Not a publisher's to read, at all. This returns a home base's entire
    # clickstream -- every reader, every article, and a markup_ratio column
    # that must never reach a publisher (#6). Any publisher key could fetch it,
    # which handed one party reader-level records belonging to another.
    #
    # Restricted to the exchange's own key, which is what the home bases' Retail
    # Agents use. Per-home-base keys are the right end state; this is the
    # correct boundary in the meantime rather than an open door.
    if authorised_for != INTERNAL:
        logger.warning("home base report refused for key belonging to %s", authorised_for)
        raise HTTPException(
            status_code=403,
            detail="Home base reports are not available to publisher keys",
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT timestamp, network_user_id, home_base_id, pub_mbr_id,
                   resource_id, page_class, service_class, markup_ratio,
                   event_type, session_id
              FROM access_events
             WHERE home_base_id = $1
               AND timestamp >= $2
               AND timestamp < $3
             ORDER BY timestamp
            """,
            home_base_id,
            period_start,
            period_end,
        )

    events = [
        EventRecord(
            timestamp=r["timestamp"],
            network_user_id=r["network_user_id"],
            home_base_id=r["home_base_id"],
            pub_mbr_id=r["pub_mbr_id"],
            resource_id=r["resource_id"],
            page_class=float(r["page_class"]),
            service_class=r["service_class"],
            markup_ratio=float(r["markup_ratio"]),
            event_type=r["event_type"],
            session_id=r["session_id"],
        )
        for r in rows
    ]

    return HomeBaseReport(
        home_base_id=home_base_id,
        period_start=period_start,
        period_end=period_end,
        total_events=len(events),
        events=events,
    )


# ── GET /log/report/publisher/{pub_mbr_id} ───────────────────────────
#
# Publishers receive ONLY aggregated data — totals grouped by home_base_id.
# CRITICAL PRIVACY REQUIREMENT: No individual user identifiers or per-user
# event rows are ever exposed to publishers.  This is a fundamental
# constraint of the Newshare architecture: publishers cannot track users
# across home bases or identify individual users from their reports.

@app.get("/log/report/publisher/{pub_mbr_id}", response_model=PublisherReport)
async def report_publisher(
    pub_mbr_id: str = Path(..., max_length=32),
    period_start: datetime = Query(..., description="ISO-8601 start of period"),
    period_end: datetime = Query(..., description="ISO-8601 end of period"),
    pool: asyncpg.Pool = Depends(_get_pool),
    authorised_for: str = Depends(verify_api_key),
) -> PublisherReport:
    """
    Aggregated report for a publisher during the specified period.

    CRITICAL PRIVACY REQUIREMENT: This endpoint returns ONLY aggregated
    totals grouped by home_base_id.  NO individual user identifiers or
    per-user event rows are ever exposed to publishers.
    """
    # A key may only read its own publisher's figures. #31 established that a
    # key may only *file* under its own member id; reading was left open, so
    # any publisher could pull a competitor's revenue with its own credentials.
    if authorised_for != INTERNAL and authorised_for != pub_mbr_id:
        logger.warning("report refused: %s asked for %s", authorised_for, pub_mbr_id)
        raise HTTPException(
            status_code=403,
            detail="This key may not read reports for that Publishing Member ID",
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            -- markup_ratio is deliberately excluded.  page_class alone is
            -- the wholesale price the publisher is owed; the home base's
            -- retail markup is its own margin and is not disclosed here.
            --
            -- reporter = 'cms' is required, not an optimisation.  Every
            -- purchase is filed twice by design -- once by the publisher and
            -- once by the reader's home base -- so counting both sides shows
            -- the publisher twice the events and twice the money.  Settlement
            -- already aggregates one side only; this report has to agree with
            -- it, or a publisher checking its figures before payout sees a
            -- total it will never be paid.
            SELECT home_base_id,
                   COUNT(*)::int                 AS total_events,
                   COALESCE(SUM(page_class), 0)  AS total_wholesale
              FROM access_events
             WHERE pub_mbr_id = $1
               AND timestamp >= $2
               AND timestamp < $3
               AND reporter = 'cms'
             GROUP BY home_base_id
             ORDER BY home_base_id
            """,
            pub_mbr_id,
            period_start,
            period_end,
        )

    aggregates = [
        PublisherAggregate(
            home_base_id=r["home_base_id"],
            total_events=r["total_events"],
            total_wholesale=float(r["total_wholesale"]),
        )
        for r in rows
    ]

    total_events = sum(a.total_events for a in aggregates)

    return PublisherReport(
        pub_mbr_id=pub_mbr_id,
        period_start=period_start,
        period_end=period_end,
        total_events=total_events,
        aggregates=aggregates,
    )


# ── GET /log/stats ───────────────────────────────────────────────────
#
# Lightweight operational statistics endpoint.  Intentionally
# unauthenticated so that monitoring tools (Prometheus, UptimeRobot, etc.)
# can poll it without needing an API key.  Returns only aggregate counts,
# no user-level data.

@app.get("/log/stats", response_model=StatsResponse)
async def stats(
    pool: asyncpg.Pool = Depends(_get_pool),
) -> StatsResponse:
    """
    Basic operational statistics.

    This endpoint is unauthenticated so monitoring tools can poll it.
    Returns total events, today's event count, and a breakdown by event type.
    """
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*)::int FROM access_events"
        )
        today_count = await conn.fetchval(
            "SELECT COUNT(*)::int FROM access_events "
            "WHERE timestamp >= CURRENT_DATE"
        )
        type_rows = await conn.fetch(
            "SELECT event_type, COUNT(*)::int AS cnt "
            "FROM access_events GROUP BY event_type"
        )

    events_by_type = {r["event_type"]: r["cnt"] for r in type_rows}

    return StatsResponse(
        total_events=total or 0,
        events_today=today_count or 0,
        events_by_type=events_by_type,
    )


# ── Run with uvicorn when executed directly ───────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
