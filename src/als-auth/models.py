"""
ALS Auth Service — Pydantic request/response models.

These models define the API contract. The ALS never stores or returns PII;
all identifiers are opaque network-level pseudonyms.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────

class TokenValidationRequest(BaseModel):
    """Body for POST /auth/validate."""
    token: str = Field(..., description="ALS-issued session JWT to validate")


# ── Responses ─────────────────────────────────────────────────────────

class TokenClaims(BaseModel):
    """Decoded claims from a valid ALS session token."""
    iss: str
    sub: str
    aud: str
    exp: int
    iat: int
    networkUserId: str
    homeBaseId: str
    networkGroupId: int
    pubMbrId: str
    sessionId: str


class TokenValidationResponse(BaseModel):
    """Returned by POST /auth/validate on success."""
    valid: bool = True
    claims: TokenClaims


class HomeBaseEntry(BaseModel):
    """A certified home base in the network."""
    id: str
    name: str
    auth_url: str


class HomeBasesResponse(BaseModel):
    """Returned by GET /auth/home-bases."""
    home_bases: list[HomeBaseEntry]


class OIDCDiscovery(BaseModel):
    """Minimal OIDC discovery document for the ALS."""
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    response_types_supported: list[str] = ["code"]
    subject_types_supported: list[str] = ["pairwise"]
    id_token_signing_alg_values_supported: list[str] = ["RS256"]


class ErrorResponse(BaseModel):
    """Generic error envelope."""
    error: str
    detail: str | None = None
