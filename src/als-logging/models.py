"""
ALS Logging Service — Pydantic models for event records and reports.

All identifiers are opaque network-level pseudonyms.  The logging service
never handles PII.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Inbound event ─────────────────────────────────────────────────────

class AccessEvent(BaseModel):
    """An access event submitted by the ALS Auth Service or a publisher."""

    networkUserId: str = Field(
        ..., max_length=128,
        description="Opaque pairwise pseudonymous user identifier",
    )
    homeBaseId: str = Field(..., max_length=32)
    pubMbrId: str = Field(..., max_length=32)
    resourceId: str = Field(
        default="",
        description="URL or identifier of the accessed resource",
    )
    pageClass: float = Field(default=0.0, ge=0.0)
    serviceClass: int = Field(default=0, ge=0)
    markupRatio: float = Field(default=1.0, ge=0.0)
    eventType: str = Field(
        ..., max_length=32,
        description="Event type: authentication | content_access | logout",
    )
    sessionId: str = Field(default="", max_length=128)


# ── Report: individual event record ──────────────────────────────────

class EventRecord(BaseModel):
    """A single event as returned in reports."""

    timestamp: datetime
    network_user_id: str
    home_base_id: str
    pub_mbr_id: str
    resource_id: str
    page_class: float
    service_class: int
    markup_ratio: float
    event_type: str
    session_id: str


class HomeBaseReport(BaseModel):
    """Full clickstream for a home base's users."""

    home_base_id: str
    period_start: datetime
    period_end: datetime
    total_events: int
    events: list[EventRecord]


# ── Report: aggregated publisher summary ──────────────────────────────

class PublisherAggregate(BaseModel):
    """Aggregated totals for a single home base within a publisher report."""

    home_base_id: str
    total_events: int
    total_page_class: float
    total_wholesale: float


class PublisherReport(BaseModel):
    """
    Aggregated report for a publisher.

    CRITICAL PRIVACY REQUIREMENT: this report contains NO individual user
    data — only totals grouped by home_base_id.
    """

    pub_mbr_id: str
    period_start: datetime
    period_end: datetime
    total_events: int
    aggregates: list[PublisherAggregate]


# ── Stats ─────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    """Basic operational statistics."""

    total_events: int
    events_today: int
    events_by_type: dict[str, int]
