"""
ALS Auth Service — Configuration via environment variables.

This module defines all configuration for the ALS Authentication Service,
which acts as the federation broker in the Newshare four-party model:

    End User  <-->  Home Base (IdSP)  <-->  ALS (this service)  <-->  Publisher

All settings are loaded from environment variables with sensible defaults
for local development.  In production, every field with a placeholder value
(e.g. "change-me-in-production") MUST be overridden via env vars or a .env file.

See also: plans/02-als-authentication-service.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class PublisherEntry:
    """
    A registered publisher (content provider) in the Newshare Network.

    Each publisher is identified by a unique ``client_id`` (used as an OIDC
    client identifier) and a ``pub_mbr_id`` (the network-level membership ID
    assigned by ITEGA).  The ``redirect_uri`` is the publisher's registered
    callback URL, used for open-redirect validation during the authorize flow.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        # OIDC client_id registered with the home base (Keycloak)
        self.client_id: str = data["client_id"]
        # OIDC client_secret shared between ALS and home base
        self.client_secret: str = data["client_secret"]
        # Publisher's registered redirect URI (used for open-redirect validation)
        self.redirect_uri: str = data["redirect_uri"]
        # ITEGA network membership identifier for this publisher
        self.pub_mbr_id: str = data["pub_mbr_id"]
        # Human-readable display name (optional, defaults to client_id)
        self.name: str = data.get("name", self.client_id)


class Settings(BaseSettings):
    """
    Application settings, populated from environment variables.

    Pydantic-settings reads env vars matching field names (case-insensitive).
    For example, ``KEYCLOAK_BASE_URL=https://auth.example`` sets keycloak_base_url.
    """

    # ── Keycloak / Home Base ──────────────────────────────────────────
    # Base URL of the Keycloak instance that serves as the prototype home base.
    # In a multi-home-base deployment, WebFinger (RFC 7033) would be used
    # for discovery instead.
    keycloak_base_url: str = "https://auth.newshare.example"
    # Keycloak realm name containing the Newshare client configuration.
    keycloak_realm: str = "newshare"

    # ── ALS identity ──────────────────────────────────────────────────
    # The externally-reachable base URL of this ALS Auth Service.
    # Used as the ``iss`` (issuer) claim in ALS-issued session JWTs and
    # as the base for OIDC discovery (/.well-known/openid-configuration).
    als_base_url: str = "https://als.newshare.example"

    # ── RSA keys for signing ALS session tokens ───────────────────────
    # Path to the PEM-encoded RSA private key used to sign session JWTs.
    als_jwt_private_key_path: str = "/etc/als/keys/private.pem"
    # Path to the PEM-encoded RSA public key (published via /.well-known/jwks.json).
    als_jwt_public_key_path: str = "/etc/als/keys/public.pem"

    # ── Downstream services ───────────────────────────────────────────
    # Internal URL of the Network Discovery Service, which holds the
    # registry of ITEGA-certified home bases.  The ALS consults it to
    # resolve a visitor to a home base and to learn that home base's
    # OIDC endpoints, rather than assuming a single configured realm.
    discovery_service_url: str = "http://localhost:8002"

    # Internal URL of the ALS Logging Service (POST /log/event).
    logging_service_url: str = "http://localhost:8001"
    # API key used to authenticate calls to the ALS Logging Service.
    # Must match the ``api_key`` setting in the logging service's config.
    # Without this, every event-log POST will be rejected with 403.
    logging_api_key: str = ""

    # ── Publisher registry ────────────────────────────────────────────
    # JSON string (inline array) or path to a JSON file containing the
    # registered publisher entries.  Each entry must have: client_id,
    # client_secret, redirect_uri, pub_mbr_id.  Optionally: name.
    publishers_config: str = "[]"

    # ── Session state ─────────────────────────────────────────────────
    # HMAC secret used to sign the ``state`` parameter that round-trips
    # through Keycloak during the authorization flow.  Must be a strong
    # random value in production (e.g. 64+ hex chars).
    session_secret: str = "change-me-in-production"

    # ── JWKS cache ────────────────────────────────────────────────────
    # How many seconds to cache the home base's JWKS before re-fetching.
    # 300 s (5 min) balances freshness with reducing load on Keycloak.
    jwks_cache_ttl: int = 300

    # ── AI agent membership ───────────────────────────────────────────
    # Path to the registry of ITEGA-certified AI agents and the business
    # rules each has agreed to.  Publishers consult this (via the ALS)
    # before serving a crawler.
    ai_agents_registry_path: str = "data/ai-agents.json"

    # Default lifetime of a crawl grant, in seconds.  An agent may keep
    # crawling one publisher without renegotiating until this expires;
    # each fulfilled request is still logged and billed individually.
    # Overridden per agent by its own agreed business rules.
    ai_grant_ttl: int = 3600

    # Where a non-member crawler is directed to establish membership.  The
    # script is specific that a refusal should point somewhere useful rather
    # than simply denying the request.
    ai_agent_signup_url: str = "https://itega.org/join"

    # ── Session token TTL ─────────────────────────────────────────────
    # Lifetime of ALS-issued session JWTs, in seconds.
    # 1800 s = 30 minutes — short enough to limit replay risk.
    session_token_ttl: int = 1800

    # ── CORS ──────────────────────────────────────────────────────────
    # Browser origins permitted to call this service directly. The
    # demonstration dashboard is served from a different host than the
    # services it exercises, so those calls are cross-origin. Listed
    # explicitly rather than wildcarded -- these endpoints answer questions
    # about membership and pricing, and arbitrary sites have no business
    # asking them from a visitor's browser.
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "https://dashboard.newshare.example",
    ]

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
