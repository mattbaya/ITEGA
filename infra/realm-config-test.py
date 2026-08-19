#!/usr/bin/env python3
"""Do the running realms match what the repository says they are?

Nothing asked this until 19 Aug 2026, and by then the answer had been no for
days. The realm files declared two clients; four were running. `pub-c` and
`dashboard` had both been added by hand with kcadm and never written back, and
because that step was applied realm by realm it was applied inconsistently --
wesmc, created a day after the other two, never got a `dashboard` client at all.
So the readers of the one home base deliberately chosen to be a co-operative
rather than a newspaper could not use the reader dashboard, and there was no
design decision behind it whatsoever (#60, #61).

Two further facts lived only inside the running server: the unmanaged-attribute
policy, without which a reader's spending limit cannot be stored (#29), and the
`dashboard` client's pairwise mapper, which is the whole of #56. A clean rebuild
from the repository would have silently dropped the first and reintroduced the
second.

What this checks, and what it deliberately does not:

  * every client the repository declares exists in the running realm
  * every client the running realm has is declared
  * every client that sees a reader has a pairwise subject mapper -- the rule
    from #56, enforced rather than remembered
  * the unmanaged-attribute policy is on

It does NOT compare secrets or salts. Those must never be in this repository:
it is public, and a committed salt means anyone who ever learns a reader's local
subject can compute their identifier at that publisher. The files carry
placeholders, and the real values live on the host and want backing up -- losing
one costs no reader and no settlement, but every publisher would meet every
reader as a stranger, permanently.

Usage:  infra/realm-config-test.py
Exit:   0 if the running realms are what the repository says.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

HOST = "deploy@auth.itega.org"
KEY = pathlib.Path.home() / ".ssh/newshare_deploy"
REALMS = pathlib.Path(__file__).parent / "vps1" / "realms"

# Clients Keycloak creates for itself. Not ours to declare.
BUILT_IN = {"account", "account-console", "admin-cli", "broker",
            "realm-management", "security-admin-console"}

PASS: list[str] = []
FAIL: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  \033[32m✓\033[0m {label:<50} {detail}")
    PASS.append(label)


def bad(label: str, detail: str = "") -> None:
    print(f"  \033[31m✗\033[0m {label:<50} {detail}")
    FAIL.append(label)


def kcadm(args: str) -> str:
    script = (
        "cd /opt/newshare/infra/vps1 && "
        "ADMIN=$(sudo grep '^KEYCLOAK_ADMIN=' .env | cut -d= -f2-) && "
        "PW=$(sudo grep '^KEYCLOAK_ADMIN_PASSWORD=' .env | cut -d= -f2-) && "
        "sudo docker exec newshare-keycloak /opt/keycloak/bin/kcadm.sh config credentials "
        "--server http://localhost:8080 --realm master --user \"$ADMIN\" --password \"$PW\" "
        ">/dev/null 2>&1 && "
        f"sudo docker exec newshare-keycloak /opt/keycloak/bin/kcadm.sh {args} 2>/dev/null"
    )
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-i", str(KEY), HOST, script],
        capture_output=True, text=True, timeout=120).stdout


def main() -> int:
    if not KEY.exists():
        print(f"  no deploy key at {KEY} — skipped")
        return 0

    files = sorted(REALMS.glob("*-realm.json"))
    if not files:
        print("  no realm files to compare against")
        return 1

    print(f"\n\033[1mDeclared realms against running ones\033[0m  ({len(files)} realms)\n")

    for path in files:
        declared = json.loads(path.read_text())
        realm = declared["realm"]
        want = {c["clientId"] for c in declared.get("clients", [])}

        # No --fields here, deliberately. kcadm's projection returns
        # protocolMappers as a list of EMPTY objects, so a check written with
        # it reported every client as lacking a pairwise mapper -- including
        # ones demonstrably carrying one. The first version of this file did
        # exactly that and would have sent someone hunting a fault that did not
        # exist, which is the same disease as a check that misses a real one.
        raw = kcadm(f"get clients -r {realm}")
        if not raw.strip():
            bad(f"{realm}: reachable", "kcadm returned nothing — authenticated?")
            continue
        try:
            live_clients = json.loads(raw)
        except json.JSONDecodeError:
            bad(f"{realm}: readable", raw.strip()[:44])
            continue

        live = {c["clientId"]: c for c in live_clients
                if c.get("clientId") not in BUILT_IN}

        missing = want - set(live)
        extra = set(live) - want
        if missing:
            bad(f"{realm}: every declared client exists", ", ".join(sorted(missing)))
        else:
            ok(f"{realm}: every declared client exists", f"{len(want)} clients")

        if extra:
            # Not cosmetic. A client running that nothing declares is one a
            # rebuild silently drops, which is exactly how #60 happened.
            bad(f"{realm}: nothing running is undeclared", ", ".join(sorted(extra)))
        else:
            ok(f"{realm}: nothing running is undeclared")

        # #56: anything that sees a reader must see a pairwise identifier.
        blind = []
        for cid, c in sorted(live.items()):
            mappers = c.get("protocolMappers") or []
            if not any("pairwise" in str(m.get("protocolMapper", "")) for m in mappers):
                blind.append(cid)
        if blind:
            bad(f"{realm}: every client gets a pairwise subject",
                ", ".join(blind) + " would receive the reader's real id")
        else:
            ok(f"{realm}: every client gets a pairwise subject", f"{len(live)} clients")

        profile = kcadm(f"get users/profile -r {realm}")
        if re.search(r'"unmanagedAttributePolicy"\s*:\s*"ENABLED"', profile):
            ok(f"{realm}: unmanaged attributes enabled", "reader thresholds can be stored")
        else:
            bad(f"{realm}: unmanaged attributes enabled",
                "a reader's spending limit cannot be saved here")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  The running realms are not what this repository says they are.\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
