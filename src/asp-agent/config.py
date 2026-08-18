"""
Retail Agent (ASP) — configuration via environment variables.

Represents the ITEGA client code a home base runs to buy content on behalf of
its readers. See plans/01-home-base-idsp-server.md (billing and retail markup)
and the wholesale-retail pricing section of the demo script.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings populated from environment variables."""

    # ── Identity ──────────────────────────────────────────────────────
    # ITEGA identifier of the home base this agent acts for.
    home_base_id: str = "HB001"
    home_base_name: str = "Publisher C Home Base"

    # ── Pricing policy ────────────────────────────────────────────────
    # Retail multiplier applied when billing this home base's own readers.
    # Never disclosed to publishers.
    markup_ratio: float = 1.1
    # Wholesale price at or below which the agent buys without negotiating.
    auto_accept_below: float = 0.10
    # Wholesale price above which the agent refuses outright.
    decline_above: float = 0.50
    # Between those bounds, counter at this fraction of the asking price.
    counter_fraction: float = 0.75

    # ── Downstream services ───────────────────────────────────────────
    # The agent files its own log report for every purchase it authorises, so
    # its record can be reconciled against the publisher's independently.
    logging_service_url: str = "http://localhost:8001"
    logging_api_key: str = ""

    # ── The home base's own directory ─────────────────────────────────
    # Used to resolve a reader's pairwise identifiers back to the reader, which
    # only this party may do. Left empty, the agent runs exactly as before and
    # the reader-facing history simply is not offered.
    #
    # Admin credentials are the wrong grant for this and are used because they
    # are what exists today. Before a pilot: a dedicated client with a service
    # account holding view-users and view-clients, and nothing else. #53.
    keycloak_url: str = ""
    keycloak_realm: str = ""
    keycloak_admin: str = ""
    keycloak_admin_password: str = ""

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
