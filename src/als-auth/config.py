"""
ALS Auth Service — Configuration via environment variables.

All settings are loaded from environment variables with sensible defaults
for local development. In production, these MUST be set explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class PublisherEntry:
    """A registered publisher in the Newshare Network."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.client_id: str = data["client_id"]
        self.client_secret: str = data["client_secret"]
        self.redirect_uri: str = data["redirect_uri"]
        self.pub_mbr_id: str = data["pub_mbr_id"]
        self.name: str = data.get("name", self.client_id)


class Settings(BaseSettings):
    """Application settings, populated from environment variables."""

    # Keycloak / Home Base
    keycloak_base_url: str = "https://auth.newshare.example"
    keycloak_realm: str = "newshare"

    # ALS identity
    als_base_url: str = "https://als.newshare.example"

    # RSA keys for signing ALS session tokens
    als_jwt_private_key_path: str = "/etc/als/keys/private.pem"
    als_jwt_public_key_path: str = "/etc/als/keys/public.pem"

    # Downstream services
    logging_service_url: str = "http://localhost:8001"

    # Publisher registry — JSON string or path to a JSON file
    publishers_config: str = "[]"

    # Secret used to encrypt temporary session state
    session_secret: str = "change-me-in-production"

    # JWKS cache TTL in seconds
    jwks_cache_ttl: int = 300

    # Session token TTL in seconds (30 minutes)
    session_token_ttl: int = 1800

    model_config = {"env_prefix": "", "case_sensitive": False}

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_base_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_auth_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/auth"

    @property
    def keycloak_token_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/token"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"

    def load_publishers(self) -> list[PublisherEntry]:
        """Parse publishers_config as inline JSON or a file path."""
        raw = self.publishers_config.strip()
        if raw.startswith("[") or raw.startswith("{"):
            data = json.loads(raw)
        else:
            data = json.loads(Path(raw).read_text())
        if isinstance(data, dict):
            data = [data]
        return [PublisherEntry(p) for p in data]

    def read_private_key(self) -> str:
        return Path(self.als_jwt_private_key_path).read_text()

    def read_public_key(self) -> str:
        return Path(self.als_jwt_public_key_path).read_text()


settings = Settings()
