"""
Retail Agent (ASP) — request/response models for the pricing exchange.

These define the wire contract for the negotiation the demo script calls the
"ITEGA dynamic pricing protocol": the content site states what it wants for a
resource, and the reader's home base — acting as their Retail Agent — accepts,
counters, or declines.

Two prices travel through this exchange and must not be confused:

  wholesale  = what the Rights Owner (publisher) asks and is owed
  retail     = wholesale * markupRatio, what the Retail Agent bills its reader

The publisher only ever states and receives the wholesale figure. The markup is
the agent's margin and is deliberately withheld from the offer response.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QuoteRequest(BaseModel):
    """
    A content site's offer to sell access to one resource.

    Sent by the publisher's ITEGA client code before it releases content
    (demo script step 28). ``wholesalePrice`` is the publisher's asking price.
    """

    networkUserId: str = Field(..., max_length=128, description="Opaque PPID of the reader")
    homeBaseId: str = Field(..., max_length=32)
    pubMbrId: str = Field(..., max_length=32, description="Publisher asking for payment")
    resourceId: str = Field(..., description="URL or identifier of the resource")
    wholesalePrice: float = Field(..., ge=0.0, description="Publisher's asking price")
    sessionId: str = Field(default="", max_length=128)
    # Set when the publisher is responding to a previous counter-offer, so the
    # agent can tell a fresh negotiation from a continuing one.
    negotiationId: str = Field(default="", max_length=64)


class QuoteResponse(BaseModel):
    """
    The Retail Agent's answer.

    ``decision`` is one of:
      - ``accept``  -- the agent authorises payment; the publisher may release
                       the content and will be settled at ``agreedPrice``.
      - ``counter`` -- the agent proposes a lower price. The publisher may
                       accept by re-quoting at that figure, or decline.
      - ``decline`` -- the agent will not authorise payment at any offered
                       price. The publisher shows the reader the refusal
                       message from script step 29.

    ``retailPrice`` is what the reader will be billed and is included so the
    reader can be shown their obligation before committing. It is returned to
    the publisher only because the publisher renders that disclosure; the
    ``markupRatio`` producing it is never disclosed.
    """

    decision: str = Field(..., description="accept | counter | decline")
    negotiationId: str = Field(..., max_length=64)
    # Present on accept: the wholesale figure the publisher will be settled at.
    agreedPrice: float | None = Field(default=None, ge=0.0)
    # Present on counter: the wholesale figure the agent is willing to pay.
    counterPrice: float | None = Field(default=None, ge=0.0)
    # Present on accept: what the reader owes their agent. Disclosure only.
    retailPrice: float | None = Field(default=None, ge=0.0)
    # Human-readable rationale, shown in the demo UI to make the exchange legible.
    reason: str = Field(default="")


class AgentPolicy(BaseModel):
    """
    A home base's standing instructions for buying content on a reader's behalf.

    In production each home base sets these for itself; the prototype loads one
    policy from configuration.
    """

    homeBaseId: str = "HB001"
    # Retail multiplier applied to the wholesale price when billing the reader.
    markupRatio: float = Field(default=1.1, ge=0.0)
    # At or below this wholesale price the agent buys without hesitation.
    autoAcceptBelow: float = Field(default=0.10, ge=0.0)
    # Above this wholesale price the agent will not buy at all.
    declineAbove: float = Field(default=0.50, ge=0.0)
    # Between the two thresholds the agent counters at this fraction of the ask.
    counterFraction: float = Field(default=0.75, gt=0.0, le=1.0)
