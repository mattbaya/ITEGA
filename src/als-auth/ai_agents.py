"""
ALS Auth Service — AI agent membership and crawl grants.

An AI answer engine is a member of the network like any other, but it does not
use a browser, cannot be redirected, and does not log in. It identifies itself
on every request, agrees a price machine-to-machine, and then crawls at volume
until a grant expires.

Two things live here:

  - **The membership table.** Which AI agents ITEGA currently certifies, and
    the business rules each has agreed to. A publisher's ITEGA client code
    consults this before serving anything to a crawler (script steps 3-5).
  - **Grants.** Once an agent has agreed a price with a publisher, it may keep
    crawling that publisher without renegotiating until the grant times out
    (steps 9-10, 13). Every fulfilled request is still logged and billed
    individually; the grant removes the handshake, not the accounting.

Why the exchange is shaped the way it is
----------------------------------------
The publisher answers an unpriced request with **HTTP 402 Payment Required**
and its terms in headers; the agent re-sends carrying its agreement. That is
our own protocol, but deliberately the same shape as x402, which is where this
would migrate if x402 becomes an operating standard. Keeping the price
agreement in a 402 exchange rather than inventing a bespoke endpoint is what
makes that migration a substitution rather than a rewrite.

Note that x402 covers payment only. Deciding whether a crawler is a member at
all -- the part below -- has no x402 equivalent today.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger("als-auth.ai-agents")

_MAX_GRANTS = 50_000


class AIAgentRegistry:
    """
    The certified-AI-agent table and the grants issued against it.

    Loaded from a JSON file so ITEGA's membership decisions stay reviewable in
    version control, the same as the home-base registry.
    """

    def __init__(self, registry_path: str, default_grant_ttl: int = 3600) -> None:
        self._path = registry_path
        self._default_ttl = default_grant_ttl
        self._agents: dict[str, dict[str, Any]] = {}
        # grant token -> {agent_mbr_id, pub_mbr_id, agreed_price, expires_at}
        self._grants: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.load()

    def load(self) -> None:
        """Read the membership table from disk."""
        try:
            data = json.loads(Path(self._path).read_text())
            self._agents = {a["agentMbrId"]: a for a in data.get("ai_agents", [])}
            logger.info("Loaded %d certified AI agent(s)", len(self._agents))
        except FileNotFoundError:
            logger.warning("AI agent registry not found at %s", self._path)
        except Exception:
            logger.exception("Failed to parse AI agent registry at %s", self._path)

    # ── membership ────────────────────────────────────────────────────

    def verify(self, agent_mbr_id: str, api_key: str) -> dict[str, Any] | None:
        """
        Check that an agent is certified, in good standing, and presenting the
        right key. Returns the agent's business rules, or None.

        The key comparison is constant-time: a timing side channel here would
        let an attacker recover a member key byte by byte and crawl on someone
        else's account.
        """
        agent = self._agents.get(agent_mbr_id)
        if agent is None:
            return None
        if agent.get("membership_status") != "active":
            logger.info("Agent %s presented but is not active", agent_mbr_id)
            return None
        if not hmac.compare_digest(str(agent.get("api_key", "")), api_key):
            logger.warning("Agent %s presented an invalid key", agent_mbr_id)
            return None
        return agent

    # ── grants ────────────────────────────────────────────────────────

    def issue_grant(
        self,
        agent_mbr_id: str,
        pub_mbr_id: str,
        agreed_price: float,
        ttl: int | None = None,
    ) -> tuple[str, int]:
        """
        Issue a crawl grant and return (token, expires_at).

        A grant is scoped to one agent at one publisher. It is not a licence to
        crawl the whole network on one handshake: another publisher's content
        is another publisher's price, and has to be agreed separately.
        """
        self._evict_expired()
        while len(self._grants) >= _MAX_GRANTS:
            evicted, _ = self._grants.popitem(last=False)
            logger.warning("Grant store full — evicted %s", evicted[:12])

        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + (ttl or self._default_ttl)
        self._grants[token] = {
            "agent_mbr_id": agent_mbr_id,
            "pub_mbr_id": pub_mbr_id,
            "agreed_price": agreed_price,
            "expires_at": expires_at,
        }
        logger.info(
            "Grant issued: %s -> %s at %s until %d",
            agent_mbr_id, pub_mbr_id, agreed_price, expires_at,
        )
        return token, expires_at

    def check_grant(self, token: str, pub_mbr_id: str) -> dict[str, Any] | None:
        """
        Validate a grant for a specific publisher.

        Returns None once expired, which is what forces the fresh membership
        check the script calls for after a timeout. Also returns None if the
        grant belongs to a different publisher, so a grant agreed cheaply at
        one site cannot be replayed against another.
        """
        grant = self._grants.get(token)
        if grant is None:
            return None
        if grant["expires_at"] <= time.time():
            self._grants.pop(token, None)
            return None
        if grant["pub_mbr_id"] != pub_mbr_id:
            logger.warning(
                "Grant for %s replayed against %s", grant["pub_mbr_id"], pub_mbr_id
            )
            return None
        return grant

    def revoke_grant(self, token: str) -> None:
        """Drop a grant — either party may close the connection early."""
        self._grants.pop(token, None)

    def _evict_expired(self) -> None:
        now = time.time()
        for token in [t for t, g in self._grants.items() if g["expires_at"] <= now]:
            self._grants.pop(token, None)

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def grant_count(self) -> int:
        return len(self._grants)
