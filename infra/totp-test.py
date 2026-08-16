#!/usr/bin/env python3
"""Prove two-factor authentication actually challenges, by using it.

Both home bases advertise TOTP. Advertising it proves nothing: the required
action can be enabled while the browser flow never reaches the OTP form, in
which case a reader sets up an authenticator app, believes they are protected,
and is signed in by password alone forever after. The only honest check is to
enrol a second factor and then try to get past it.

So this creates a throwaway reader, enrols an authenticator, and asserts three
things in order:

  1. Enrolment is offered and completes.
  2. A later sign-in stops for a code rather than going straight through.
  3. A wrong code is refused, and the right one is accepted.

Point 3 matters most. A challenge that appears and then accepts anything is
worse than no challenge, because it is believed.

The test user is created and deleted here and exists only for the run. Its
password is generated at run time, is never printed, and never touches disk.

Requires ssh access to auth.itega.org as deploy.

Usage:  infra/totp-test.py
Exit:   0 if the second factor is real, 1 otherwise.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import http.cookiejar
import re
import secrets
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK = "https://auth.itega.org"

# Both home bases are checked, because they are configured separately and a
# second factor that works at one proves nothing about the other.
REALMS = ("publisher-c", "newshare")
REALM = REALMS[0]
HOST = "deploy@auth.itega.org"
KEY = "~/.ssh/newshare_deploy"
TEST_USER = "totp-probe@itega.org"

PASS: list[str] = []
FAIL: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  \033[32m✓\033[0m {label:<44} {detail}")
    PASS.append(label)


def bad(label: str, detail: str = "") -> None:
    print(f"  \033[31m✗\033[0m {label:<44} {detail}")
    FAIL.append(label)


# ── TOTP (RFC 6238) ──────────────────────────────────────────────────
# Six digits, SHA-1, thirty-second step: the realm's own OTP policy, and what
# every authenticator app implements. Written out rather than imported so the
# test has no dependency the servers do not already have.

def totp(key: bytes, when: float | None = None, step: int = 30) -> str:
    counter = int((when if when is not None else time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


# ── the reader's browser ─────────────────────────────────────────────

def session():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(op, url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "newshare-totp-test"})
    try:
        with op.open(req, timeout=30) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.geturl(), e.read().decode("utf-8", "replace")


def post(op, url: str, data: dict, referer: str = "") -> tuple[str, str]:
    hdrs = {"Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "newshare-totp-test"}
    if referer:
        hdrs["Referer"] = referer
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(), headers=hdrs)
    try:
        with op.open(req, timeout=30) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.geturl(), e.read().decode("utf-8", "replace")


def form_action(body: str) -> str | None:
    m = re.search(r'<form[^>]+action="([^"]+)"', body)
    return html.unescape(m.group(1)) if m else None


def hidden_fields(body: str) -> dict[str, str]:
    """Every hidden input in the first form — Keycloak carries state in them."""
    return {
        n: html.unescape(v)
        for n, v in re.findall(
            r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', body)
    }


# ── the throwaway reader ─────────────────────────────────────────────

def kcadm(script: str) -> subprocess.CompletedProcess:
    """Run a kcadm script on the auth host. Admin credentials stay there."""
    preamble = (
        "set -euo pipefail\n"
        "E=/opt/newshare/infra/vps1/.env\n"
        'K="docker exec newshare-keycloak /opt/keycloak/bin/kcadm.sh"\n'
        '$K config credentials --server http://localhost:8080 --realm master '
        '--user "$(grep -m1 \'^KEYCLOAK_ADMIN=\' $E | cut -d= -f2-)" '
        '--password "$(grep -m1 \'^KEYCLOAK_ADMIN_PASSWORD=\' $E | cut -d= -f2-)" '
        ">/dev/null 2>&1\n"
    )
    return subprocess.run(
        ["ssh", "-i", KEY, "-o", "BatchMode=yes", HOST, "sudo bash -s"],
        input=preamble + script, capture_output=True, text=True, timeout=120)


def create_probe_user(password: str) -> str | None:
    """
    Create the test reader, already owing an authenticator setup.

    The password travels inside the script, which reaches the far end over the
    ssh channel and is never written to disk or passed as an argument, so it
    stays out of the process table on both machines. It cannot be read from
    stdin: the script itself is arriving that way, and a `read` would swallow
    the next line of the script instead.
    """
    script = f"""
id=$($K get users -r {REALM} -q username={TEST_USER} --fields id --format csv --noquotes 2>/dev/null | head -1)
[ -n "$id" ] && $K delete "users/$id" -r {REALM} >/dev/null 2>&1
$K create users -r {REALM} -s username={TEST_USER} -s email={TEST_USER} \
    -s enabled=true -s emailVerified=true \
    -s 'requiredActions=["CONFIGURE_TOTP"]' 2>&1 | head -2
id=$($K get users -r {REALM} -q username={TEST_USER} --fields id --format csv --noquotes 2>/dev/null | head -1)
[ -n "$id" ] || {{ echo "CREATE_FAILED"; exit 1; }}
$K set-password -r {REALM} --userid "$id" --new-password '{password}' 2>&1 | head -2
echo "USERID=$id"
"""
    r = kcadm(script)
    m = re.search(r"USERID=(\S+)", (r.stdout or "") + (r.stderr or ""))
    if not m:
        detail = ((r.stdout or "") + (r.stderr or "")).strip().replace("\n", " ")
        print(f"      {detail[:160]}")
        return None
    return m.group(1)


def delete_probe_user() -> None:
    kcadm(f"""
id=$($K get users -r {REALM} -q username={TEST_USER} --fields id --format csv --noquotes 2>/dev/null | head -1)
[ -n "$id" ] && $K delete "users/$id" -r {REALM} >/dev/null 2>&1
echo done
""")


# ── the journey ──────────────────────────────────────────────────────

def sign_in(op, password: str) -> tuple[str, str]:
    """Username and password only. Returns the page that follows."""
    url, body = get(op, f"{KEYCLOAK}/realms/{REALM}/account/")
    action = form_action(body)
    if not action:
        return "", ""
    return post(op, action,
                {"username": TEST_USER, "password": password, "credentialId": ""},
                referer=url)


def main() -> int:
    global REALM
    for realm in (sys.argv[1:] or REALMS):
        REALM = realm
        if check_realm() != 0:
            return 1
    print()
    if FAIL:
        print(f"  \033[31m{len(PASS)} passed, {len(FAIL)} failed\033[0m\n")
        return 1
    print(f"  \033[32m{len(PASS)} passed, 0 failed\033[0m\n")
    return 0


def check_realm() -> int:
    password = secrets.token_urlsafe(18)      # never printed, never stored

    print(f"\nENROLLING A SECOND FACTOR  ({REALM})")
    if not create_probe_user(password):
        bad("test reader created", "could not create the user")
        return 1
    ok("test reader created")

    try:
        op = session()
        url, body = sign_in(op, password)
        if not body:
            bad("password sign-in reaches enrolment")
            return 1

        # The shared secret the phone would scan. This theme renders it as a
        # QR image and carries the same value in a hidden field, which is what
        # a real authenticator ends up holding either way.
        fields = hidden_fields(body)
        secret = fields.get("totpSecret", "")
        if not secret:
            m = re.search(r'<span[^>]*id="kc-totp-secret-key"[^>]*>([^<]+)</span>', body)
            secret = m.group(1).replace(" ", "") if m else ""
        if not secret:
            bad("enrolment is offered", "no authenticator secret on the page")
            return 1

        # Keycloak's hidden field carries the secret as raw characters; the
        # base32 string a phone scans is that value encoded, not the value
        # itself. Hashing the base32 text instead of the bytes it stands for
        # yields codes that look right and are always rejected.
        key = secret.encode("ascii")
        ok("enrolment is offered", f"{len(secret)}-character secret")

        action = form_action(body)
        fields.update({"totp": totp(key), "userLabel": "probe"})
        url, body = post(op, action, fields, referer=url)
        if "kc-totp-settings-form" in body:
            bad("enrolment accepts a valid code", "rejected its own secret")
            return 1
        ok("enrolment completes")

        # ── the point of the exercise ────────────────────────────────
        print("\nSIGNING IN AGAIN")
        op = session()
        url, body = sign_in(op, password)

        challenged = ("kc-otp-login-form" in body
                      or re.search(r'name="otp"', body)
                      or "One-time code" in body
                      or "Authenticator code" in body)
        if not challenged:
            bad("the password alone is not enough",
                "signed straight in — the second factor is decorative")
            return 1
        ok("the password alone is not enough", "a code was demanded")

        # A challenge that accepts anything is worse than none, because it is
        # trusted. Offer a code that is certainly wrong.
        action = form_action(body)
        fields = hidden_fields(body)
        wrong = "000000" if totp(key) != "000000" else "111111"
        _, refused = post(op, action, dict(fields, otp=wrong), referer=url)
        if re.search(r'name="otp"', refused) or "nvalid" in refused:
            ok("a wrong code is refused")
        else:
            bad("a wrong code is refused", "it let us through")
            return 1

        # And the right one gets in. Take a fresh code: the enrolment code may
        # be in the same 30-second step, which Keycloak refuses to reuse.
        action = form_action(refused) or action
        fields = hidden_fields(refused) or fields
        time.sleep(31 - (time.time() % 30))
        _, body = post(op, action, dict(fields, otp=totp(key)), referer=url)
        if re.search(r'name="otp"', body):
            bad("the right code is accepted", "still asking for a code")
        else:
            ok("the right code is accepted")

    finally:
        delete_probe_user()
        ok("test reader removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
