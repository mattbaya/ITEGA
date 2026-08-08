"""
ALS Logging Service — Pydantic models for event records and reports.

All identifiers are opaque network-level pseudonyms (PPIDs).  The logging
service never handles PII — that responsibility belongs exclusively to the
home base (IdSP).

Naming conventions
------------------
- **API layer (JSON):** camelCase field names (e.g. ``networkUserId``,
  ``pageClass``, ``eventType``).  This matches the Newshare spec's
  canonical field naming.
- **Database layer (SQL):** snake_case column names (e.g.
  ``network_user_id``, ``page_class``, ``event_type``).  This follows
  PostgreSQL conventions and improves readability in SQL queries.

The translation between the two conventions happens at the INSERT boundary
in main.py (event.networkUserId -> $2 for network_user_id column) and at
the SELECT boundary in report construction (r["network_user_id"] -> field).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Inbound event ─────────────────────────────────────────────────────

class AccessEvent(BaseModel):
    """
    An access event submitted by the ALS Auth Service or a publisher plugin.

    The ALS Auth Service submits ``authentication`` and ``logout`` events.
    The publisher WordPress plugin submits ``content_access`` events when
    a user views a protected page.  Future event types (``ad_view``,
    ``subscription_credit``, ``reward``) are reserved for Phase 2.
    """

    # Opaque pairwise pseudonymous user identifier (PPID).
    # Different at every publisher — cannot be correlated across sites.
    networkUserId: str = Field(
        ..., max_length=128,
        description="Opaque pairwise pseudonymous user identifier (PPID)",
    )
    # ITEGA-assigned identifier of the home base that authenticated the user.
    homeBaseId: str = Field(..., max_length=32)
    # ITEGA-assigned network membership ID of the publisher.
    pubMbrId: str = Field(..., max_length=32)
    # URL or identifier of the accessed resource (empty for auth events).
    resourceId: str = Field(
        default="",
        description="URL or identifier of the accessed resource",
    )
    # Wholesale price tier assigned by the publisher to the content page.
    # 0.0 for non-metered events (authentication, logout).
    pageClass: float = Field(default=0.0, ge=0.0)
    # Service classification code (reserved for future use).
    serviceClass: int = Field(default=0, ge=0)
    # Retail markup ratio applied by the home base when billing its own
    # user.  Retail price = pageClass * markupRatio; the wholesale value
    # settled between the parties is pageClass alone.
    markupRatio: float = Field(default=1.0, ge=0.0)
    # Event type — one of the following:
    #   - "content_access"       — user viewed a protected content page
    #   - "authentication"       — user completed SSO login
    #   - "logout"               — user logged out
    #   - "ad_view"              — user viewed an ad impression (Phase 2)
    #   - "subscription_credit"  — subscription credited to publisher (Phase 2)
    #   - "reward"               — user reward / loyalty event (Phase 2)
    eventType: str = Field(
        ..., max_length=32,
        description=(
            "Event type: content_access | authentication | logout | "
            "ad_view | subscription_credit | reward"
        ),
    )
    # Unique session identifier correlating this event to an auth session.
    sessionId: str = Field(default="", max_length=128)


# ── Report: individual event record ──────────────────────────────────
#
# Used in home-base reports (full clickstream).  Field names are
# snake_case here because they map directly from PostgreSQL column names.

class EventRecord(BaseModel):
    """
    A single event as returned in home-base reports.

    Note: Field names use snake_case (matching the DB schema), not
    camelCase (which is the API inbound convention).  This is intentional
    -- report output reflects the storage schema for consistency with
    the settlement batch job's CSV exports.
    """

    timestamp: datetime         # Server-assigned UTC timestamp
    network_user_id: str        # PPID (opaque, pairwise per publisher)
    home_base_id: str           # Home base that authenticated the user
    pub_mbr_id: str             # Publisher membership ID
    resource_id: str            # URL or content identifier
    page_class: float           # Wholesale price tier
    service_class: int          # Service classification (reserved)
    markup_ratio: float         # Home base retail markup
    event_type: str             # Event type enum
    session_id: str             # Correlating session identifier


class HomeBaseReport(BaseModel):
    """
    Full clickstream for a home base's users during a time period.

    Home bases receive full per-event detail because they are the identity
    provider and billing counterpart — they already know the user's real
    identity and need the data for billing reconciliation.
    """

    home_base_id: str
    period_start: datetime
    period_end: datetime
    total_events: int
    events: list[EventRecord]


# ── Report: aggregated publisher summary ──────────────────────────────
#
# Publishers only see aggregated data.  No individual user identifiers
# or per-user event rows are included.

class PublisherAggregate(BaseModel):
    """
    Aggregated totals for a single home base within a publisher report.

    ``total_wholesale`` = SUM(page_class): the price this publisher asked
    and is owed.  The home base's ``markup_ratio`` is deliberately not
    represented here — the retail price it charges its own users is its
    margin, and the Rights Owner is not entitled to see it.
    """

    home_base_id: str           # Which home base the aggregate covers
    total_events: int           # Number of events from this home base
    total_wholesale: float      # Sum of page_class (wholesale owed)


class PublisherReport(BaseModel):
    """
    Aggregated report for a publisher.

    CRITICAL PRIVACY REQUIREMENT: this report contains NO individual user
    data -- only totals grouped by home_base_id.  Publishers cannot
    identify specific users from this data.
    """

    pub_mbr_id: str
    period_start: datetime
    period_end: datetime
    total_events: int
    aggregates: list[PublisherAggregate]


# ── Stats ─────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    """
    Basic operational statistics returned by GET /log/stats.

    Unauthenticated — contains no user-level data, only aggregate counts.
    """

    total_events: int                   # All-time event count
    events_today: int                   # Events since midnight UTC
    events_by_type: dict[str, int]      # Breakdown by event_type enum
