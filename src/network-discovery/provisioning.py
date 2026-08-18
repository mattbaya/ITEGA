"""Publisher self-provisioning.

== What this solves ==

A publisher installs the WordPress plugin and it works. No Publishing Member
ID typed in, no API key pasted into a settings form, and — the point — no
secret anywhere in the distributable, which is a public download.

ITEGA registers a publisher's domains first; that is the certification step,
and in a real network it is where the paperwork, the banking details and the
governance sit. The plugin then calls home on activation, names the domain it
is running on, and receives the credentials for it.

== Why the store is separate from registry.json ==

``registry.json`` is served to anyone who asks, at /discovery/publishers. It
is the network's public directory. Credentials cannot live in it, so they live
here, in a file that is never served and never committed.

== Proving the domain ==

An endpoint that answers "what are the credentials for greylockglass.com?"
cannot tell a plugin from a stranger: the domain arrives as a parameter, and a
parameter is a claim rather than proof.

So the caller proves it. The plugin picks a random nonce, publishes it on the
site at ``/.well-known/newshare-challenge``, and then asks to be provisioned.
This service fetches that URL over TLS and checks the nonce matches. An
impostor can say they are greylockglass.com; they cannot make greylockglass.com
serve their nonce.

Nothing secret travels in either direction during the exchange -- the nonce is
public and single-use, and the credentials are only sent once the fetch has
succeeded. The site's own key material never leaves the site, because there is
none: possession is demonstrated by control of the domain, which is the thing
actually being asserted.

This is the HTTP-01 challenge from ACME, and it is used for the same reason
Let's Encrypt uses it: it is the cheapest check that cannot be faked by
anyone who does not run the site.

Because it re-proves control every time, a reinstall simply works. There is
nothing for an operator to unlock.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# One writer at a time: two activations arriving together must not both be
# told they were first.
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise(domain: str) -> str:
    """Reduce a domain to the form the store is keyed by.

    A plugin may report ``https://www.example.org/``; the operator registered
    ``example.org``. Lower-cased, scheme and path stripped, leading ``www.``
    removed, port dropped.
    """
    d = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/")[0].split("?")[0]
    d = d.split(":")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


class Provisioning:
    """The registered-domains file, loaded and rewritten in place."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.entries: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            logger.warning("No provisioning store at %s", self.path)
            return
        except Exception:
            logger.exception("Could not parse provisioning store at %s", self.path)
            return
        self.entries = {normalise(k): v for k, v in raw.get("domains", {}).items()}
        claimed = sum(1 for e in self.entries.values() if e.get("claimed_at"))
        logger.info(
            "Loaded provisioning: %d domain(s), %d already claimed",
            len(self.entries), claimed,
        )

    def _save(self) -> None:
        body = json.dumps({"domains": self.entries}, indent=2) + "\n"

        # Write beside the target and rename, so a crash mid-write cannot leave
        # the store truncated and every publisher unprovisionable.
        #
        # That rename fails if the target is a bind-mounted single file, which
        # is how this was first deployed: Docker mounts the file itself, so
        # renaming onto it is renaming onto a mount point and the kernel
        # answers EBUSY. The directory is mounted instead now, but the
        # fallback stays -- the failure surfaced only in production, and an
        # unwritable store means no publisher can ever install the plugin.
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(body)
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning(
                "Atomic rename unavailable (%s); writing in place", exc)
            tmp.unlink(missing_ok=True)
            self.path.write_text(body)

    def keys_by_pub_mbr_id(self) -> dict[str, str]:
        """API key -> Publishing Member ID, for the logging service to verify."""
        return {
            e["api_key"]: e["pub_mbr_id"]
            for e in self.entries.values()
            if e.get("api_key") and e.get("pub_mbr_id")
        }

    def issue(self, domain: str, caller: str, verifier) -> tuple[dict[str, Any] | None, str]:
        """Verify control of a registered domain, then hand over credentials.

        ``verifier`` is called with the normalised domain and must return True
        only if the challenge was served correctly. It is injected so the
        network fetch can be exercised in tests without one.

        Returns ``(entry, "")`` on success, or ``(None, reason)`` where reason
        is ``unregistered``, ``unverified`` or ``revoked``.
        """
        key = normalise(domain)
        entry = self.entries.get(key)
        if entry is None:
            logger.warning("Provisioning refused: %s is not registered", key)
            return None, "unregistered"
        if entry.get("revoked"):
            logger.warning("Provisioning refused: %s is revoked", key)
            return None, "revoked"

        if not verifier(key):
            logger.warning("Provisioning refused: %s failed the challenge", key)
            return None, "unverified"

        with _lock:
            entry.setdefault("issued", [])
            entry["issued"].append({"at": _now(), "from": caller})
            # Keep the tail only. This is an audit trail, not a log file, and
            # an unbounded list would grow every time a site is rebuilt.
            entry["issued"] = entry["issued"][-20:]
            self._save()
        logger.info("Provisioned %s as %s to %s", key, entry["pub_mbr_id"], caller)
        return entry, ""

    def revoke(self, domain: str, revoked: bool = True) -> bool:
        """Stop (or resume) issuing credentials for a domain.

        For a publisher leaving the network, or a domain that changed hands.
        Verification alone would otherwise keep letting the current owner in.
        """
        key = normalise(domain)
        with _lock:
            entry = self.entries.get(key)
            if entry is None:
                return False
            entry["revoked"] = revoked
            self._save()
            logger.info("%s %s", "Revoked" if revoked else "Reinstated", key)
            return True


def new_api_key() -> str:
    """A fresh per-publisher key. 32 bytes, URL-safe."""
    return secrets.token_urlsafe(32)


# ── The challenge fetch ───────────────────────────────────────────────
#
# Where the plugin publishes its nonce. A path under /.well-known/ rather
# than a plugin route, so it stays valid if the site later moves to another
# CMS, and so a publisher can satisfy it by hand with a static file if their
# WordPress cannot serve it.
CHALLENGE_PATH = "/.well-known/newshare-challenge"


def verify_domain(domain: str, nonce: str, timeout: float = 10.0) -> bool:
    """Fetch the challenge from ``domain`` and check it carries ``nonce``.

    Deliberately strict, because this function is the whole of the proof:

    * HTTPS only. Plain HTTP is trivially spoofed by anyone on the path, and
      every site in this network already has a certificate.
    * Redirects are not followed. A redirect can leave the domain being
      proved, and "example.org redirects to attacker.example" would otherwise
      prove the attacker controls example.org.
    * The response is size-capped and compared exactly after stripping
      whitespace, so a page that happens to contain the nonce somewhere in its
      body does not pass.
    """
    import urllib.error
    import urllib.request

    if not nonce or len(nonce) < 16:
        return False

    url = f"https://{domain}{CHALLENGE_PATH}"

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # noqa: D102
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(
        url, headers={"User-Agent": "ITEGA-Newshare-Provisioning/1.0"})

    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            body = response.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        logger.info("Challenge for %s returned HTTP %s", domain, exc.code)
        return False
    except Exception as exc:  # noqa: BLE001 -- DNS, TLS, timeout, refused
        logger.info("Challenge for %s could not be fetched: %s", domain, exc)
        return False

    return secrets.compare_digest(body.strip(), nonce.strip())
