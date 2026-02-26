"""
ALS Logging Service — FastAPI application.

Records access events into a TimescaleDB hypertable and exposes reporting
endpoints.  All data uses opaque, pseudonymous identifiers — no PII is
ever stored.

Endpoints
---------
POST /log/event                            — Record an access event
GET  /log/report/home-base/{home_base_id}  — Full clickstream for a home base
GET  /log/report/publisher/{pub_mbr_id}    — Aggregated report for a publisher
GET  /log/stats                            — Basic operational statistics
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
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

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, raising 503 if unavailable."""
    if _pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return _pool


# ── Lifespan ──────────────────────────────────────────────────────────

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
                    session_id      VARCHAR(128)    NOT NULL DEFAULT ''
                );
            """)
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

async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Validate the shared API key on protected endpoints."""
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


# ── Health ────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz() -> dict[str, str]:
    if _pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return {"status": "ok"}


# ── POST /log/event ──────────────────────────────────────────────────

@app.post("/log/event", status_code=202)
async def log_event(
    event: AccessEvent,
    pool: asyncpg.Pool = Depends(_get_pool),
    _api_key: str = Depends(verify_api_key),
) -> dict[str, str]:
    """
    Record an access event.

    The server adds the authoritative timestamp; the client cannot
    back-date events.
    """
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO access_events (
                timestamp, network_user_id, home_base_id, pub_mbr_id,
                resource_id, page_class, service_class, markup_ratio,
                event_type, session_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
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
        )

    logger.info(
        "Logged %s event: user=%s pub=%s",
        event.eventType,
        event.networkUserId[:12] + "…",
        event.pubMbrId,
    )
    return {"status": "accepted", "timestamp": now.isoformat()}


# ── GET /log/report/home-base/{home_base_id} ─────────────────────────

@app.get("/log/report/home-base/{home_base_id}", response_model=HomeBaseReport)
async def report_home_base(
    home_base_id: str = Path(..., max_length=32),
    period_start: datetime = Query(..., description="ISO-8601 start of period"),
    period_end: datetime = Query(..., description="ISO-8601 end of period"),
    pool: asyncpg.Pool = Depends(_get_pool),
    _api_key: str = Depends(verify_api_key),
) -> HomeBaseReport:
    """
    Full clickstream for a home base's users during the specified period.

    This includes every individual event, because the home base has a
    legitimate operational need to see its own users' activity (they are
    the identity provider and billing counterpart).
    """
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

@app.get("/log/report/publisher/{pub_mbr_id}", response_model=PublisherReport)
async def report_publisher(
    pub_mbr_id: str = Path(..., max_length=32),
    period_start: datetime = Query(..., description="ISO-8601 start of period"),
    period_end: datetime = Query(..., description="ISO-8601 end of period"),
    pool: asyncpg.Pool = Depends(_get_pool),
    _api_key: str = Depends(verify_api_key),
) -> PublisherReport:
    """
    Aggregated report for a publisher during the specified period.

    CRITICAL PRIVACY REQUIREMENT: This endpoint returns ONLY aggregated
    totals grouped by home_base_id.  NO individual user identifiers or
    per-user event rows are ever exposed to publishers.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT home_base_id,
                   COUNT(*)::int                     AS total_events,
                   COALESCE(SUM(page_class), 0)      AS total_page_class,
                   COALESCE(SUM(page_class * markup_ratio), 0) AS total_wholesale
              FROM access_events
             WHERE pub_mbr_id = $1
               AND timestamp >= $2
               AND timestamp < $3
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
            total_page_class=float(r["total_page_class"]),
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

@app.get("/log/stats", response_model=StatsResponse)
async def stats(
    pool: asyncpg.Pool = Depends(_get_pool),
) -> StatsResponse:
    """
    Basic operational statistics.

    This endpoint is unauthenticated so monitoring tools can poll it.
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
