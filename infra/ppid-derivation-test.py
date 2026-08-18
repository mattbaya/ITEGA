#!/usr/bin/env python3
"""Prove the home base can reconstruct its own readers' pairwise identifiers.

Bill Densmore asked for two things on 18 Aug 2026: a reader's consolidated
history across the network (#28), and a threshold the reader sets themselves
(#29). Both need one capability the system does not have -- a home base able to
tell that two pairwise identifiers, at two different publishers, belong to the
same person (#53).

Nobody else may have that ability. The publishers must not, the exchange must
not, and the whole architecture rests on it being impossible for them. The home
base can, because it issued the identifiers, and this file proves it can by
reconstructing them from first principles and checking them against what the
publishers independently recorded.

The derivation, which is Keycloak's and had to be reproduced exactly:

    sub = UUID.nameUUIDFromBytes( SHA256( sector + localSub + salt ) )

where `salt` is the client's own `pairwiseSubAlgorithmSalt`, `sector` is the
host of its redirect URI (Keycloak's fallback when no sectorIdentifierUri is
configured), and `nameUUIDFromBytes` is Java's MD5-based version-3 UUID -- which
is why every identifier in this network has a 3 in its third group.

WHY THIS FILE EXISTS AS A TEST RATHER THAN A LIBRARY

Get any part of that wrong and the reverse index comes out empty, or -- far
worse -- maps a reader onto somebody else's reading history. Both failures are
silent: an empty history is indistinguishable from a reader who has read
nothing. This project's recurring defect is a check that cannot observe what it
claims (#18, #43, #50), so the derivation is checked the only way that actually
observes it: against identifiers recorded independently, by different software,
on different machines, at the moment those readers really signed in.

If this ever fails, nothing built on the derivation should ship until it passes.

Needs the deploy key for the Keycloak host and ssh access to the publisher sites.

Usage:  infra/ppid-derivation-test.py
Exit:   0 if every derived identifier matches what the publisher recorded.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys
import urllib.parse
import uuid

KC_HOST = "deploy@auth.itega.org"
KC_KEY = pathlib.Path.home() / ".ssh/newshare_deploy"
REALM = "publisher-c"
CREDS = pathlib.Path.home() / "newshare-bill-credentials.txt"

# Keycloak client -> the publisher site that records what it issues.
PUBLISHERS = {
    "pub-a": ("barharbor", "public_html", "Bar Harbor Info"),
    "pub-b": ("northberkshire", "public_html", "North Berkshire"),
}

PASS: list[str] = []
FAIL: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  \033[32m✓\033[0m {label:<46} {detail}")
    PASS.append(label)


def bad(label: str, detail: str = "") -> None:
    print(f"  \033[31m✗\033[0m {label:<46} {detail}")
    FAIL.append(label)


def kc(script: str) -> str:
    """Run a kcadm script on the Keycloak host, authenticating first.

    kcadm exits zero and prints nothing when it is not authenticated, which is
    its own small trap -- an earlier session read that silence as "no such user"
    and reported the opposite of the truth.
    """
    preamble = (
        "cd /opt/newshare/infra/vps1 && "
        "ADMIN=$(sudo grep '^KEYCLOAK_ADMIN=' .env | cut -d= -f2-) && "
        "PW=$(sudo grep '^KEYCLOAK_ADMIN_PASSWORD=' .env | cut -d= -f2-) && "
        "sudo docker exec newshare-keycloak /opt/keycloak/bin/kcadm.sh config credentials "
        "--server http://localhost:8080 --realm master --user \"$ADMIN\" --password \"$PW\" "
        ">/dev/null 2>&1 && "
    )
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-i", str(KC_KEY), KC_HOST, preamble + script],
        capture_output=True, text=True, timeout=120)
    return out.stdout


def kcadm(args: str) -> str:
    return kc(f"sudo docker exec newshare-keycloak /opt/keycloak/bin/kcadm.sh {args} 2>/dev/null")


def pairwise_sub(sector: str, local_sub: str, salt: str) -> str:
    """Keycloak's oidc-sha256-pairwise-sub-mapper, reproduced."""
    digest = hashlib.sha256((sector + local_sub + salt).encode()).digest()
    return str(uuid.UUID(bytes=hashlib.md5(digest).digest(), version=3))


def client_config(client_id: str) -> tuple[str, str] | None:
    """(sector identifier, salt) for a publisher's client."""
    ident = kcadm(f"get clients -r {REALM} -q clientId={client_id} --fields id")
    m = re.search(r'"id"\s*:\s*"([^"]+)"', ident)
    if not m:
        return None
    uid = m.group(1)

    detail = kcadm(f"get clients/{uid} -r {REALM} --fields redirectUris")
    redirect = re.search(r'"(https?://[^"]+)"', detail)
    if not redirect:
        return None
    # No sectorIdentifierUri is configured, so Keycloak falls back to the host
    # of the redirect URI. Every publisher redirects through the exchange, so
    # this is the same for all of them -- the salt is what separates them.
    sector = urllib.parse.urlparse(redirect.group(1)).netloc

    mappers = kcadm(f"get clients/{uid}/protocol-mappers/models -r {REALM}")
    salt = re.search(r'"pairwiseSubAlgorithmSalt"\s*:\s*"([^"]+)"', mappers)
    if not salt:
        return None
    return sector, salt.group(1)


def recorded_at(account: str, docroot: str, network_user_id: str) -> bool:
    """Did that publisher's WordPress really create this reader?"""
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", f"{account}@svaha.com",
         f"export PATH=$HOME/bin:$PATH; cd $HOME/{docroot}; "
         f"wp user get newshare_{network_user_id} --field=ID"],
        capture_output=True, text=True, timeout=120)
    return out.stdout.strip().isdigit()


def main() -> int:
    if not KC_KEY.exists():
        print(f"  no deploy key at {KC_KEY} — cannot reach Keycloak")
        return 1
    if not CREDS.exists():
        print(f"  no credentials file at {CREDS}")
        return 1

    block = CREDS.read_text().split("HOME BASE 1", 1)[1]
    username = re.search(r"username:\s*(\S+)", block).group(1)

    users = kcadm(f"get users -r {REALM} -q username={username} --fields id")
    m = re.search(r'"id"\s*:\s*"([^"]+)"', users)
    if not m:
        print(f"  could not resolve {username} in realm {REALM} — is kcadm authenticated?")
        return 1
    local_sub = m.group(1)

    print(f"\n\033[1mOne reader, seen from every publisher\033[0m  (realm {REALM})\n")
    derived: dict[str, str] = {}

    for client_id, (account, docroot, name) in PUBLISHERS.items():
        cfg = client_config(client_id)
        if not cfg:
            bad(f"{name}: client {client_id} readable", "no pairwise mapper or redirect URI")
            continue
        sector, salt = cfg
        sub = pairwise_sub(sector, local_sub, salt)
        derived[name] = sub

        if recorded_at(account, docroot, sub):
            ok(f"{name}: derived id is the one it recorded", sub[:18] + "…")
        else:
            bad(f"{name}: derived id is the one it recorded",
                f"{sub[:18]}… is not a reader there")

    # The same reader must look like different people to different publishers.
    # If this ever collapses, the derivation is not the only thing broken.
    if len(derived) >= 2:
        values = list(derived.values())
        if len(set(values)) == len(values):
            ok("the publishers see different people", " vs ".join(v[:8] for v in values))
        else:
            bad("the publishers see different people", "two publishers share an identifier")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    if not FAIL:
        print("  The home base can rebuild the map. Nobody else can. (#53)\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
