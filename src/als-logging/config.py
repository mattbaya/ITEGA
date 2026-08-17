"""
ALS Logging Service — Configuration via environment variables.

This module defines all configuration for the ALS Logging Service, which
records content-access and authentication events into a PostgreSQL /
TimescaleDB database.  The logging service is component #3 in the Newshare
architecture and serves as the authoritative data source for the
settlement batch job.

All settings are loaded from environment variables (case-insensitive) via
pydantic-settings.  In production, every field with a placeholder value
(e.g. "change-me-in-production") MUST be overridden.

See also: plans/03-als-logging-service.md
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings populated from environment variables."""

    # ── Database ──────────────────────────────────────────────────────
    # PostgreSQL / TimescaleDB connection string.  The database must
    # have the TimescaleDB extension installed for hypertable support;
    # the service falls back to a plain table if the extension is absent.
    database_url: str = "postgresql://als_logger:password@localhost:5432/als_logs"

    # ── Authentication ────────────────────────────────────────────────
    # Shared API key that internal callers (ALS Auth Service, settlement
    # scripts) must send in the ``X-API-Key`` header.  The ALS Auth
    # Service reads this same value from its ``logging_api_key`` setting.
    # MUST be a strong random value in production.
    api_key: str = "change-me-in-production"

    # Per-publisher API keys, written by the discovery service when it
    # provisions a publisher's plugin. Each key authorises events for exactly
    # one Publishing Member ID; the ``api_key`` above stays as the internal
    # key for the Auth Service and the settlement scripts, which legitimately
    # act for every publisher.
    publisher_keys_path: str = "data/provisioning.json"

    # Where to fetch the exchange's public keys, so a reader asking for their
    # own record can be authenticated by the session token they already hold
    # rather than by a shared secret a browser must never be given.
    als_base_url: str = "https://als.itega.org"

    # ── Connection pool ───────────────────────────────────────────────
    # Minimum number of idle connections maintained by asyncpg.
    db_min_connections: int = 2
    # Maximum number of connections.  Sized for the pilot's expected
    # concurrency (~50 users); increase for production scale.
    db_max_connections: int = 10

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
