"""
ALS Auth Service — Network Discovery client.

The ALS does not hold its own list of home bases. ITEGA's Network Discovery
Service is the registry of certified members, and this module is the thin
client the ALS uses to consult it (see src/network-discovery/).

Results are cached briefly: the registry changes only when ITEGA certifies or
suspends a member, so a short TTL keeps the authorize path fast without
letting a revoked home base linger.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("als-auth.discovery")


class DiscoveryClient:
    """Reads the certified-member registry from the Network Discovery Service."""

    def __init__(self, base_url: str, ttl: int = 300) -> None:
        self._base_url = base_url.rstrip("/")
        self._ttl = ttl
        self._home_bases: list[dict[str, Any]] = []
        self._last_refresh: float = 0.0

    async def home_bases(self) -> list[dict[str, Any]]:
        """All certified home bases, refreshing the cache when stale."""
        if not self._home_bases or (time.time() - self._last_refresh) > self._ttl:
            await self._refresh()
        return self._home_bases

    async def get(self, home_base_id: str) -> dict[str, Any] | None:
        """A single certified home base by ITEGA id, or None if unknown."""
        for hb in await self.home_bases():
            if hb.get("id") == home_base_id:
                return hb
        return None

    async def publisher_named(self, q: str) -> dict[str, Any] | None:
        """
        A certified *publisher* whose name resembles what the visitor typed.

        Asked so the chooser can tell someone they have named a newspaper rather
        than a home base. Bill typed "Bar Harbor" into this field and was shown
        two options he had no way to choose between; the fault was the screen's,
        not his, because nothing on it distinguished the paper he was reading
        from the organisation that keeps his account.
        """
        needle = q.strip().lower()
        if len(needle) < 3:
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/discovery/publishers")
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        for pub in data if isinstance(data, list) else data.get("publishers", []):
            name = str(pub.get("name", "")).lower()
            if name and (needle in name or name in needle):
                return pub
        return None

    async def resolve(self, q: str = "", client_ip: str = "") -> dict[str, Any]:
        """
        Resolve a visitor to a home base (demo script steps 20-24).

        Returns the discovery service's lookup response: an ``exact`` flag,
        ordered ``matches``, and a ``default_signup`` home base to offer when
        nothing matched. On transport failure returns an empty result rather
        than raising, so the caller can still present the full chooser list.
        """
        url = f"{self._base_url}/discovery/home-bases/resolve"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, params={"q": q, "client_ip": client_ip})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Home-base resolve failed: %s", exc)
            return {"exact": False, "matches": [], "default_signup": None}

    async def _refresh(self) -> None:
        url = f"{self._base_url}/discovery/home-bases"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                self._home_bases = resp.json()
                self._last_refresh = time.time()
                logger.info("Loaded %d home base(s) from discovery", len(self._home_bases))
        except httpx.HTTPError as exc:
            # Keep any previously-loaded registry rather than failing the
            # authorize path outright; an empty list simply means the chooser
            # has nothing to offer, which the caller reports as a 503.
            logger.error("Failed to reach discovery service: %s", exc)
