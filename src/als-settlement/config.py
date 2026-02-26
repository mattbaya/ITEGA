"""
ALS Settlement Service — Configuration via environment variables.

This module defines all configuration for the ALS Settlement batch job,
which computes financial obligations between home bases and publishers
based on metered content-access events logged by the ALS Logging Service.

The settlement script reads from the als_logs database (access_events
hypertable) and writes results to the als_settlement database.  Both
databases typically reside on the same PostgreSQL instance but use
separate roles with appropriate permissions (reader vs. writer).

All settings are loaded from environment variables (case-insensitive) via
pydantic-settings.  In production, every field with a placeholder value
MUST be overridden.

See also: plans/04-als-settlement-service.md
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settlement batch job settings populated from environment variables."""

    # ── Database connections ──────────────────────────────────────────
    # Read-only connection to the als_logs database (source of truth for
    # access events).  Uses the ``als_reader`` role which has SELECT-only
    # permissions on the access_events table/hypertable.
    als_logs_database_url: str = (
        "postgresql://als_reader:password@localhost:5432/als_logs"
    )

    # Read-write connection to the als_settlement database (destination
    # for settlement results).  Uses the ``als_settler`` role which has
    # INSERT/UPDATE/CREATE TABLE permissions.
    als_settlement_database_url: str = (
        "postgresql://als_settler:password@localhost:5432/als_settlement"
    )

    # ── ITEGA governance fee ──────────────────────────────────────────
    # The ITEGA fee is expressed as a decimal fraction of the wholesale
    # value.  For example, 0.015 = 1.5%.  This fee funds ITEGA's
    # governance operations (analogous to interchange fees in a card
    # network).  The fee is deducted from the publisher credit side,
    # not added to the home-base debit side.
    itega_fee_pct: float = 0.015

    # ── Report output ─────────────────────────────────────────────────
    # Directory where settlement report files (JSON summary, per-home-base
    # CSVs, per-publisher CSVs) are written.  Created automatically if
    # it does not exist.
    reports_dir: str = "reports"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
