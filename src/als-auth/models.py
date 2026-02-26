"""
ALS Auth Service — Pydantic request/response models.

These models define the API contract for the ALS Authentication Service.
The ALS never stores or returns PII; all identifiers are opaque network-level
pseudonyms (PPIDs).  The models below map directly to the JSON request and
response bodies documented in plans/02-als-authentication-service.md.

Naming convention:
  - Field names use camelCase in the JSON API layer (matching the Newshare
    spec's field-name conventions: networkUserId, homeBaseId, etc.)
  - Standard OIDC claims (iss, sub, aud, exp, iat) are lowercase per RFC 7519.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────

class TokenValidationRequest(BaseModel):
    """
    Body for POST /auth/validate.

    The publisher's WordPress plugin sends this after receiving an ALS
    session token via the POST callback.  The ``token`` field contains
    the compact JWS string (header.payload.signature).
    """
    token: str = Field(..., description="ALS-issued session JWT to validate")


# ── Responses ─────────────────────────────────────────────────────────

class TokenClaims(BaseModel):
    """
    Decoded claims from a valid ALS session token.

    Standard OIDC claims (RFC 7519):
      - iss: Issuer — the ALS base URL.
      - sub: Subject — the pairwise pseudonymous user ID (PPID).
      - aud: Audience — the publisher's pub_mbr_id.
      - exp: Expiration time (Unix timestamp).
      - iat: Issued-at time (Unix timestamp).

    Newshare-specific custom claims:
      - networkUserId: Same as ``sub`` — the PPID.  Duplicated for clarity
        in downstream systems that expect the Newshare field name.
      - homeBaseId: Identifies which home base (IdSP) authenticated the user.
      - networkGroupId: Bitmask encoding the user's subscription tier(s).
        Publishers compare this against their page's required tier to decide
        whether to grant access.
      - pubMbrId: ITEGA network membership ID of the publisher.
      - sessionId: Unique identifier for this authentication session, used
        for logging and settlement correlation.
    """
    iss: str                    # Issuer (ALS base URL)
    sub: str                    # Subject (PPID — pairwise per publisher)
    aud: str                    # Audience (pub_mbr_id)
    exp: int                    # Expiration (Unix epoch seconds)
    iat: int                    # Issued-at (Unix epoch seconds)
    networkUserId: str          # PPID (same as sub)
    homeBaseId: str             # Home base that authenticated the user
    networkGroupId: int         # Subscription tier bitmask
    pubMbrId: str               # Publisher network membership ID
    sessionId: str              # Unique session identifier


class TokenValidationResponse(BaseModel):
    """
    Returned by POST /auth/validate on success.

    The publisher plugin checks ``valid`` and then reads
    ``claims.networkGroupId`` to enforce access control.
    """
    valid: bool = True
    claims: TokenClaims


class HomeBaseEntry(BaseModel):
    """
    A certified home base in the Newshare Network.

    Each home base is an ITEGA-approved Identity Service Provider (IdSP)
    that runs Keycloak (or an equivalent OIDC provider) and manages user
    registration, authentication, and subscription billing.
    """
    id: str                     # ITEGA-assigned home base identifier (e.g. "HB001")
    name: str                   # Human-readable display name
    auth_url: str               # OIDC authorization endpoint URL


class HomeBasesResponse(BaseModel):
    """Returned by GET /auth/home-bases."""
    home_bases: list[HomeBaseEntry]


class OIDCDiscovery(BaseModel):
    """
    Minimal OIDC discovery document for the ALS.

    Published at /.well-known/openid-configuration per OpenID Connect
    Discovery 1.0.  Note that the ALS acts as a federation broker, not
    a standard OIDC Provider — see the endpoint docstring in main.py
    for details on the token_endpoint semantics.
    """
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    response_types_supported: list[str] = ["code"]
    # "pairwise" indicates the ALS issues PPIDs, not global subject IDs.
    subject_types_supported: list[str] = ["pairwise"]
    id_token_signing_alg_values_supported: list[str] = ["RS256"]


class ErrorResponse(BaseModel):
    """Generic error envelope returned on 4xx/5xx responses."""
    error: str
    detail: str | None = None
