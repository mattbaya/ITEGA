"""
ALS Auth Service — request/response models for the AI agent handshake.

These carry no reader data. An AI agent acts for a business, not a person, so
there is no pairwise identifier and nothing to keep pseudonymous: the whole
point is that ITEGA and the publisher both know exactly which company is
crawling and what it agreed to pay.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentVerifyRequest(BaseModel):
    """
    A publisher asking whether a crawler is a member in good standing.

    Sent by the publisher's ITEGA client code on seeing agent credentials
    (script step 3).
    """
    agentMbrId: str = Field(..., max_length=64)
    apiKey: str = Field(..., max_length=256)
    pubMbrId: str = Field(..., max_length=32, description="Publisher being crawled")
    resourceId: str = Field(default="", description="Resource being requested")


class BusinessRules(BaseModel):
    """The terms an agent has agreed to as a condition of membership."""
    maxPricePerResource: float = Field(default=0.0, ge=0.0)
    grantTtlSeconds: int = Field(default=3600, ge=0)
    settlementTerms: str = Field(default="")
    purpose: str = Field(default="")


class AgentVerifyResponse(BaseModel):
    """
    The Authenticator's answer.

    When ``member`` is false the publisher rejects the request and points the
    caller at how to join, rather than simply refusing (script steps 4, 14).
    """
    member: bool
    agentMbrId: str = ""
    name: str = ""
    businessRules: BusinessRules | None = None
    # Where to send a non-member so the rejection is useful rather than a wall.
    signupUrl: str = ""
    reason: str = ""


class GrantRequest(BaseModel):
    """
    A publisher recording that an agent accepted its price.

    Issued after the agent confirms, so subsequent requests need no further
    handshake until the grant expires (steps 9-10).
    """
    agentMbrId: str = Field(..., max_length=64)
    apiKey: str = Field(..., max_length=256)
    pubMbrId: str = Field(..., max_length=32)
    agreedPrice: float = Field(..., ge=0.0)


class GrantResponse(BaseModel):
    """A crawl grant, scoped to one agent at one publisher."""
    grant: str
    expiresAt: int
    agreedPrice: float


class GrantCheckRequest(BaseModel):
    """A publisher checking whether a presented grant is still good."""
    grant: str = Field(..., max_length=256)
    pubMbrId: str = Field(..., max_length=32)


class GrantCheckResponse(BaseModel):
    """
    Whether a grant is still valid.

    ``valid`` false means the timeout has passed (or the grant belongs to
    another publisher), and the agent must re-authenticate from the start —
    which is the behaviour the script calls for at step 13.
    """
    valid: bool
    agentMbrId: str = ""
    agreedPrice: float = 0.0
    expiresAt: int = 0
