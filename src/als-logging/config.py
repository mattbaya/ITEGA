"""
ALS Logging Service — Configuration via environment variables.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings populated from environment variables."""

    # PostgreSQL / TimescaleDB connection string
    database_url: str = "postgresql://als_logger:password@localhost:5432/als_logs"

    # API key for authenticating internal callers
    api_key: str = "change-me-in-production"

    # Connection pool sizing
    db_min_connections: int = 2
    db_max_connections: int = 10

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
