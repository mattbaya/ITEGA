"""
ALS Settlement Service — Configuration via environment variables.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settlement batch job settings populated from environment variables."""

    # Read-only connection to the als_logs database (TimescaleDB on VPS 2)
    als_logs_database_url: str = (
        "postgresql://als_reader:password@localhost:5432/als_logs"
    )

    # Read-write connection to the als_settlement database (VPS 2)
    als_settlement_database_url: str = (
        "postgresql://als_settler:password@localhost:5432/als_settlement"
    )

    # ITEGA governance fee as a decimal fraction (1.5 % = 0.015)
    itega_fee_pct: float = 0.015

    # Directory where settlement reports are written
    reports_dir: str = "reports"

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
