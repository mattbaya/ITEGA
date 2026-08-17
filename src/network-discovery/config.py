"""
Network Discovery Service — Configuration via environment variables.

See also: plans/06-network-discovery-service.md
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings populated from environment variables."""

    # Externally-reachable base URL of this service. Used as the `issuer`
    # in the network-wide OIDC discovery document.
    discovery_base_url: str = "https://network.itega.example"

    # Path to the JSON registry of certified home bases and publishers.
    # A flat file is sufficient at pilot scale (a handful of members) and
    # keeps ITEGA's certification decisions reviewable in version control.
    registry_path: str = "data/registry.json"

    # Registered publisher domains and their credentials. Deliberately a
    # different file from the registry: the registry is served to anyone who
    # asks, and this holds per-publisher API keys. Never committed, never
    # served -- only read by the /provision endpoint.
    provisioning_path: str = "data/provisioning.json"

    # Name of the network, surfaced in the discovery document.
    network_name: str = "Newshare Network"

    # ── CORS ──────────────────────────────────────────────────────────
    # Browser origins permitted to call this service directly. The
    # demonstration dashboard is served from a different host than the
    # services it exercises, so those calls are cross-origin. Listed
    # explicitly rather than wildcarded -- these endpoints answer questions
    # about membership and pricing, and arbitrary sites have no business
    # asking them from a visitor's browser.
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "https://dashboard.itega.org",
    ]

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
