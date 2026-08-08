"""
Network Discovery Service — Pydantic models.

These mirror the registry data model in plans/06-network-discovery-service.md.
The registry contains no user data of any kind — only ITEGA certification
records for member organizations.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HomeBase(BaseModel):
    """
    A certified home base (IdSP) in the Newshare Network.

    ``publishing_member_id`` is the ITEGA-issued identifier a user may type
    into the Authenticator's home-base lookup form when they know it
    (demo script step 20).
    """
    id: str
    name: str
    publishing_member_id: str
    oidc_issuer: str
    jwks_uri: str
    auth_url: str
    certification_status: str = "active"
    certification_tier: str = "idsp"
    # Optional signup URL, used when offering an unmatched visitor a place
    # to establish an account (demo script step 24).
    signup_url: str = ""
    # Optional IP prefixes hinting that a visitor is likely served by this
    # home base. Demo-grade heuristic only -- see resolve_by_ip() in main.py.
    ip_hints: list[str] = Field(default_factory=list)


class Publisher(BaseModel):
    """A certified content-vending publisher (CMS) in the network."""
    id: str
    name: str
    publishing_member_id: str
    domain: str
    certification_status: str = "active"
    certification_tier: str = "content_publisher"


class Registry(BaseModel):
    """The full certified-member registry."""
    network: str = "Newshare Network"
    version: str = "1.0"
    governed_by: str = "ITEGA"
    home_bases: list[HomeBase] = Field(default_factory=list)
    publishers: list[Publisher] = Field(default_factory=list)


class HomeBaseLookupResponse(BaseModel):
    """
    Returned by GET /discovery/home-bases/resolve.

    ``matches`` is ordered best-first. ``exact`` indicates the caller
    supplied an identifier that resolved unambiguously, so the Authenticator
    can skip the chooser UI and redirect straight to the home base.
    """
    exact: bool = False
    matches: list[HomeBase] = Field(default_factory=list)
    # Home base to offer for sign-up when nothing matched (script step 24).
    default_signup: HomeBase | None = None


class NetworkDiscovery(BaseModel):
    """Network-wide discovery document served at the well-known ITEGA URL."""
    network: str
    issuer: str
    governed_by: str
    home_bases_endpoint: str
    publishers_endpoint: str
    resolve_endpoint: str
    webfinger_endpoint: str
