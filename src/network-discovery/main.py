"""
Network Discovery Service — FastAPI application.

The directory of the Newshare Network: which organizations ITEGA has
certified as home bases (IdSPs) and as content publishers (CMS). This is
the trust anchor for the four-party model — the ALS Auth Service consults
it to learn where a user's home base lives and which public keys to trust.

It is the network analogue of DNS: logically central, physically trivial,
and read-only to everyone except ITEGA governance.

Endpoints
---------
GET /discovery/home-bases            -- List certified home bases
GET /discovery/home-bases/{id}       -- Single home base by ITEGA id
GET /discovery/home-bases/resolve    -- Resolve a home base from user input or IP
GET /discovery/publishers            -- List certified publishers
GET /.well-known/newshare-network    -- Network-wide discovery document
GET /.well-known/webfinger           -- WebFinger (RFC 7033) home-site discovery
GET /healthz                         -- Health check
"""

from __future__ import annotations

import ipaddress
import json
import logging
from pathlib import Path as FilePath

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from config import settings
from models import (
    HomeBase,
    HomeBaseLookupResponse,
    NetworkDiscovery,
    Publisher,
    Registry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("network-discovery")

app = FastAPI(
    title="Network Discovery Service",
    version="0.1.0",
    description="Newshare Network — Certified member directory (ITEGA)",
)

# ── CORS ─────────────────────────────────────────────────────────────
#
# The demonstration dashboard calls this service directly from a browser, and
# in production it is served from a different host, so those requests are
# cross-origin. Origins are listed explicitly rather than wildcarded: these
# endpoints answer questions about network membership and pricing, and there
# is no reason for arbitrary sites to be able to ask them from a visitor's
# browser.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_registry: Registry = Registry()


@app.on_event("startup")
async def _startup() -> None:
    global _registry
    try:
        raw = json.loads(FilePath(settings.registry_path).read_text())
        _registry = Registry(**raw)
        logger.info(
            "Loaded registry: %d home base(s), %d publisher(s)",
            len(_registry.home_bases),
            len(_registry.publishers),
        )
    except FileNotFoundError:
        logger.warning("Registry file not found at %s", settings.registry_path)
    except Exception:
        logger.exception("Failed to parse registry at %s", settings.registry_path)


def _active_home_bases() -> list[HomeBase]:
    return [h for h in _registry.home_bases if h.certification_status == "active"]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "home_bases": str(len(_active_home_bases()))}


@app.get("/discovery/home-bases", response_model=list[HomeBase])
async def list_home_bases() -> list[HomeBase]:
    """Every home base ITEGA currently certifies."""
    return _active_home_bases()


@app.get("/discovery/home-bases/resolve", response_model=HomeBaseLookupResponse)
async def resolve_home_base(
    q: str = Query("", description="Home base name or Publishing Member ID"),
    client_ip: str = Query("", description="Visitor IP, for candidate suggestion"),
) -> HomeBaseLookupResponse:
    """
    Resolve a visitor to their home base (demo script steps 20-24).

    Resolution order, most-confident first:
      1. Exact match on ITEGA id or Publishing Member ID -- skip the chooser.
      2. Substring match on name -- present the candidates.
      3. IP-prefix hint -- suggest likely candidates.
      4. Nothing matched -- return a default home base to offer for sign-up.
    """
    active = _active_home_bases()
    needle = q.strip().lower()

    if needle:
        for hb in active:
            if needle in (hb.id.lower(), hb.publishing_member_id.lower()):
                return HomeBaseLookupResponse(exact=True, matches=[hb])

        name_matches = [hb for hb in active if needle in hb.name.lower()]
        if name_matches:
            return HomeBaseLookupResponse(
                exact=len(name_matches) == 1,
                matches=name_matches,
            )

    if client_ip:
        ip_matches = [hb for hb in active if _ip_matches(client_ip, hb.ip_hints)]
        if ip_matches:
            return HomeBaseLookupResponse(exact=False, matches=ip_matches)

    return HomeBaseLookupResponse(
        exact=False,
        matches=[],
        default_signup=next((hb for hb in active if hb.signup_url), None),
    )


def _ip_matches(client_ip: str, hints: list[str]) -> bool:
    """
    Check whether an address falls inside any hinted CIDR block.

    This is a demonstration heuristic standing in for the real thing: a
    production network would resolve a home base from a user-supplied
    identifier or a prior affiliation, never from IP alone. Malformed
    input simply fails to match rather than raising.
    """
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for hint in hints:
        try:
            if addr in ipaddress.ip_network(hint, strict=False):
                return True
        except ValueError:
            continue
    return False


@app.get("/discovery/home-bases/{home_base_id}", response_model=HomeBase)
async def get_home_base(home_base_id: str = Path(..., max_length=32)) -> HomeBase:
    """Look up a single certified home base by its ITEGA identifier."""
    for hb in _active_home_bases():
        if hb.id == home_base_id:
            return hb
    raise HTTPException(status_code=404, detail=f"Unknown home base: {home_base_id}")


@app.get("/discovery/publishers", response_model=list[Publisher])
async def list_publishers() -> list[Publisher]:
    """Every content publisher ITEGA currently certifies."""
    return [p for p in _registry.publishers if p.certification_status == "active"]


@app.get("/.well-known/newshare-network", response_model=NetworkDiscovery)
async def network_discovery() -> NetworkDiscovery:
    """Network-wide discovery document — the entry point for new members."""
    base = settings.discovery_base_url
    return NetworkDiscovery(
        network=settings.network_name,
        issuer=base,
        governed_by=_registry.governed_by,
        home_bases_endpoint=f"{base}/discovery/home-bases",
        publishers_endpoint=f"{base}/discovery/publishers",
        resolve_endpoint=f"{base}/discovery/home-bases/resolve",
        webfinger_endpoint=f"{base}/.well-known/webfinger",
    )


@app.get("/.well-known/webfinger")
async def webfinger(
    resource: str = Query(..., description="acct: or https: URI to resolve"),
) -> JSONResponse:
    """
    WebFinger (RFC 7033) home-site discovery.

    Given ``acct:someone@example-home-base.org``, return the OIDC issuer of
    the home base serving that domain. This lets a publisher discover where
    to send a user without the ALS having to know anything about them.
    """
    domain = resource.rsplit("@", 1)[-1].strip().lower()
    if not domain:
        raise HTTPException(status_code=400, detail="Malformed resource parameter")

    for hb in _active_home_bases():
        if domain in hb.oidc_issuer.lower():
            return JSONResponse({
                "subject": resource,
                "links": [{
                    "rel": "http://openid.net/specs/connect/1.0/issuer",
                    "href": hb.oidc_issuer,
                }],
            })

    raise HTTPException(status_code=404, detail="No home base found for resource")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info",
    )
