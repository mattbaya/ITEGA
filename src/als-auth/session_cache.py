"""
ALS Auth Service — the Authenticator's cache of recently authenticated readers.

The demo script has the Authenticator check its own store *first* when an
authentication request arrives, and only fall back to discovering the reader's
home base when nothing fresh is found. This is what makes a single login work
across every site in the network for the life of the session.

What is cached, and what deliberately is not
--------------------------------------------
Each entry records that *this browser* has an authenticated session with *that
home base*, plus any publisher-scoped session tokens already issued to it. It
holds no name, no email, and no home-base-level user identifier.

Two rules govern reuse, and the second is the one that matters:

  - **Same publisher, fresh token** -> reuse it outright. No round trip at all.
  - **Different publisher** -> we still go back to the home base, every time.

The second rule is not an optimisation we failed to make. A reader's identifier
is *pairwise*: they are a different opaque person at every publisher, and only
the home base can mint that identifier. Skipping the home base to save a redirect
would mean the ALS inventing the identifier instead, which would either hand the
same id to two publishers -- destroying the un-correlatability the whole
architecture exists to provide -- or quietly move identity issuance from the home
base to ITEGA, which is exactly the thing ITEGA is not supposed to do.

So what the cache actually buys is skipping the *chooser* and the login prompt:
the reader is sent straight back to the home base they already use, which
recognises them and answers without asking anything. From the reader's side that
is indistinguishable from not being asked to log in again, which is the behaviour
the demonstration is meant to show.

On the cookie
-------------
Recognising a returning browser requires some state in that browser. This is a
first-party cookie on the Authenticator's own domain containing nothing but an
opaque random handle -- no identifiers, no claims, no home base name. The
network's "no cookies" rule is about carrying authentication state between
parties, which this does not do: the handle is meaningless to anyone but this
service, and a publisher never sees it. The script calls for exactly this at
steps 10 and 40.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("als-auth.session-cache")

# Bound the store so a flood of authentications cannot exhaust memory.
_MAX_ENTRIES = 10_000


class AuthenticatorSessionCache:
    """
    Temporary store of authenticated readers, keyed by an opaque handle.

    Single-threaded async use, so no locking. A production deployment would
    move this to Redis so that several Authenticator instances share it; the
    script explicitly puts multi-authenticator coordination out of scope.
    """

    def __init__(self, ttl: int = 1800) -> None:
        self._ttl = ttl
        self._entries: OrderedDict[str, dict[str, Any]] = OrderedDict()

    # ── writes ────────────────────────────────────────────────────────

    def remember(self, handle: str, home_base_id: str, id_token: str = "") -> str:
        """
        Record that this browser is authenticated with a home base.

        Returns the handle to store in the reader's cookie, generating a fresh
        one when the caller has none.

        The home base's ID token is kept so that a "log out everywhere" can be
        presented to that home base as an ``id_token_hint``, which is how
        OpenID Connect RP-Initiated Logout identifies the session being ended.
        It holds the pairwise identifier and the tier bitmask -- no name, no
        address, nothing that could identify the reader -- and dies with the
        entry.
        """
        self._evict_expired()

        if not handle or handle not in self._entries:
            handle = secrets.token_urlsafe(32)

        while len(self._entries) >= _MAX_ENTRIES:
            evicted, _ = self._entries.popitem(last=False)
            logger.warning("Session cache full — evicted %s", evicted[:12])

        # A reader crossing to a second publisher calls this again with a
        # handle they already hold. Keep the tokens already issued to them --
        # rebuilding the entry from scratch would throw away the first
        # publisher's token and send them back through a round trip they had
        # already completed.
        existing = self._entries.get(handle, {})

        self._entries[handle] = {
            "home_base_id": home_base_id,
            # Refreshed on each authentication, as before: a reader who has
            # just proved themselves again should not be timed out on the
            # clock of the session that preceded it.
            "created_at": time.time(),
            # pub_mbr_id -> (session_token, expires_at)
            "tokens": existing.get("tokens", {}),
            "id_token": id_token or existing.get("id_token", ""),
        }
        return handle

    def store_token(
        self,
        handle: str,
        pub_mbr_id: str,
        token: str,
        expires_at: float,
    ) -> None:
        """Associate an issued session token with this reader and publisher."""
        entry = self._entries.get(handle)
        if entry is None:
            return
        entry["tokens"][pub_mbr_id] = (token, expires_at)

    # ── reads ─────────────────────────────────────────────────────────

    def home_base_for(self, handle: str) -> str | None:
        """
        The home base this browser authenticated with, if the entry is fresh.

        Used to skip the chooser and send a returning reader straight back to
        the home base they already use.
        """
        entry = self._fresh_entry(handle)
        return entry["home_base_id"] if entry else None

    def token_for(self, handle: str, pub_mbr_id: str) -> str | None:
        """
        A still-valid token previously issued to this reader for this publisher.

        Only ever returns a token minted for this same publisher, so the
        pairwise identifier inside it stays correct. Returns None once the token
        is within a small margin of expiry, so a publisher is never handed a
        token that dies mid-request.
        """
        entry = self._fresh_entry(handle)
        if entry is None:
            return None

        cached = entry["tokens"].get(pub_mbr_id)
        if cached is None:
            return None

        token, expires_at = cached
        if expires_at - time.time() < 30:
            entry["tokens"].pop(pub_mbr_id, None)
            return None
        return token

    def id_token_for(self, handle: str) -> str | None:
        """
        The home base's ID token for this browser, if the entry is fresh.

        Used only as an ``id_token_hint`` when ending the session at the home
        base, so that it knows which session to end without being told who the
        reader is a second time.
        """
        entry = self._fresh_entry(handle)
        return entry.get("id_token") or None if entry else None

    # ── logout ────────────────────────────────────────────────────────

    def forget_token(self, handle: str, pub_mbr_id: str) -> bool:
        """
        Drop the token cached for one publisher, leaving the rest intact.

        This is "log out here". Without it the publisher's own logout is
        cosmetic: the reader clicks a gated article, the Authenticator finds a
        still-valid token for that publisher and hands it straight back, and
        they are signed in again without ever seeing a login screen.

        Returns whether a token was actually dropped.
        """
        entry = self._entries.get(handle)
        if entry is None:
            return False
        return entry["tokens"].pop(pub_mbr_id, None) is not None

    def forget(self, handle: str) -> None:
        """
        Drop the entry entirely — "log out everywhere".

        Ends the reader's network session: every publisher's cached token goes
        with it, and the next visit anywhere starts at the chooser. The session
        at the home base itself is separate, and is ended by redirecting the
        reader there; see the logout endpoint.
        """
        self._entries.pop(handle, None)

    # ── housekeeping ──────────────────────────────────────────────────

    def _fresh_entry(self, handle: str) -> dict[str, Any] | None:
        """Return the entry for a handle, or None if absent or stale."""
        if not handle:
            return None
        entry = self._entries.get(handle)
        if entry is None:
            return None
        if time.time() - entry["created_at"] > self._ttl:
            self._entries.pop(handle, None)
            return None
        return entry

    def _evict_expired(self) -> None:
        now = time.time()
        stale = [
            k for k, v in self._entries.items()
            if now - v["created_at"] > self._ttl
        ]
        for k in stale:
            self._entries.pop(k, None)

    @property
    def size(self) -> int:
        return len(self._entries)
