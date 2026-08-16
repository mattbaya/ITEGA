#!/usr/bin/env python3
"""Walk the reader's authenticated journey end to end, for real.

`smoke-test.sh` proves every door is reachable. This proves a reader can get
through one: read past the meter, sign in at a home base, have the code
exchanged, come back with a session, read the article, and then be recognised
at the *second* publisher without signing in again.

Seven separate bugs hid behind the fact that nobody had ever done this. Each
one alone stops a reader dead, and each looked fine from the hop before it, so
this walks every step and asserts on the result rather than the redirect.

Credentials come from ~/newshare-bill-credentials.txt and are never printed.

Usage:  infra/journey-test.py
Exit:   0 if the journey completes, 1 otherwise.
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import base64
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ALS = "https://als.itega.org"
PUBLISHERS = {
    "barharbor":      ("Bar Harbor",        "https://barharbor.info"),
    "northberkshire": ("North Berkshire",   "https://northberkshire.org"),
    "wesmc":          ("West End Sentinel", "https://wesmc.org"),
}

# ssh account and document root per site. West End Sentinel is an addon domain
# under the northberkshire account, so it shares the login and not the docroot.
SITE_HOSTS = {
    "barharbor":      ("barharbor",      "public_html"),
    "northberkshire": ("northberkshire", "public_html"),
    "wesmc":          ("northberkshire", "wesmc.org"),
}
HOME_BASE = "ITEGA-PC-0001"

PASS: list[str] = []
FAIL: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  \033[32m✓\033[0m {label:<44} {detail}")
    PASS.append(label)


def bad(label: str, detail: str = "") -> None:
    print(f"  \033[31m✗\033[0m {label:<44} {detail}")
    FAIL.append(label)


def credentials() -> tuple[str, str]:
    p = pathlib.Path.home() / "newshare-bill-credentials.txt"
    if not p.exists():
        sys.exit(f"  no credentials file at {p}")
    block = p.read_text().split("HOME BASE 1", 1)[1]
    return (re.search(r"username:\s*(\S+)", block).group(1),
            re.search(r"password:\s*(\S+)", block).group(1))


def session():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def get(op, url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "newshare-journey-test"})
    try:
        with op.open(req, timeout=30) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.geturl(), e.read().decode("utf-8", "replace")


def post(op, url: str, data: dict, referer: str = "") -> tuple[str, str]:
    hdrs = {"Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "newshare-journey-test"}
    if referer:
        hdrs["Referer"] = referer
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers=hdrs)
    try:
        with op.open(req, timeout=30) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.geturl(), e.read().decode("utf-8", "replace")


def priced_articles(host: str, n: int = 4, offset: int = 0) -> list[str]:
    """
    Articles chosen the way a reader chooses them.

    This used to ask for posts carrying a price -- `--meta_key=newshare_page_class`
    -- and then check that those posts were gated. It selected its inputs by the
    property under test, so it could only ever confirm what the seed data had
    already arranged, and it passed for weeks while 9,774 of the 9,778 articles on
    the two sites were free to everyone. Bill found that in about four clicks.

    Now it takes published posts in ordinary order and makes no assumption about
    what is configured on them, which is the only way the meter can actually be
    said to work.
    """
    account, docroot = SITE_HOSTS.get(host, (host, "public_html"))
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", f"{account}@svaha.com",
         f"export PATH=~/bin:$PATH; cd ~/{docroot}; wp post list --post_type=post "
         f"--post_status=publish --posts_per_page={n} --offset={offset} --field=url"],
        capture_output=True, text=True, timeout=90).stdout.split()
    return out


def post_count(host: str) -> int:
    """How many published posts this site has."""
    account, docroot = SITE_HOSTS.get(host, (host, "public_html"))
    out = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", f"{account}@svaha.com",
         f"export PATH=~/bin:$PATH; cd ~/{docroot}; wp post list --post_type=post "
         "--post_status=publish --posts_per_page=-1 --format=count"],
        capture_output=True, text=True, timeout=90).stdout.strip()
    return int(out) if out.isdigit() else 0


def archive_is_metered(host: str, label: str) -> None:
    """
    The meter must hold deep in the archive, not just on the newest few.

    A reader arriving from a search result lands on a five-year-old story, and
    that is the request the site has to charge for. Reads four articles from well
    inside the archive and asserts the fourth is gated.
    """
    # As deep as this site goes. A 12-post co-op has no article sixty back, and
    # demanding one would fail a site that is behaving perfectly.
    total = post_count(host)
    offset = max(0, min(60, total - 4))
    urls = priced_articles(host, n=4, offset=offset)
    if len(urls) < 4:
        bad(f"{label}: has four articles to read", f"{total} published")
        return
    op, _ = session()
    for u in urls[:3]:
        get(op, u)
    _, body = get(op, urls[3])
    if "newshare-login-btn" in body:
        ok(f"{label}: the archive is metered too",
           f"gate closed on the fourth, {offset} deep")
    else:
        bad(f"{label}: the archive is metered too",
            "an old article was served free — most of the site is not for sale")


def every_home_base_works(host: str) -> None:
    """
    Sign in through every certified home base, not just the first.

    The suite used to walk one home base -- Publisher C -- and nothing ever
    exercised the second. Its Keycloak client held a different secret from the
    one the exchange presents, so every sign-in through it failed with a 401 and
    a raw error page, and had done since the day it was created. Bill found it
    by choosing the other option in the chooser, which is the first thing any
    reader with an account elsewhere will do.

    A network whose whole claim is "any home base, any publisher" cannot be
    tested against one home base.
    """
    try:
        with urllib.request.urlopen(
                "https://network.itega.org/discovery/home-bases", timeout=20) as r:
            bases = json.loads(r.read().decode())
    except Exception as exc:                      # noqa: BLE001
        bad("home base registry reachable", str(exc)[:50])
        return

    user, pw = credentials()
    articles = priced_articles(host)
    if len(articles) < 4:
        bad("articles available for the home-base sweep")
        return

    for hb in bases:
        hb_id = hb.get("publishing_member_id", "")
        name = hb.get("name") or hb_id
        op, _ = session()
        for u in articles[:3]:
            get(op, u)
        _, body = get(op, articles[3])
        m = re.search(r'href="([^"]*newshare_login=1[^"]*)"', body)
        if not m:
            bad(f"{name}: reaches the gate")
            continue
        _, chooser = get(op, html.unescape(m.group(1)))
        hrefs = [html.unescape(c.group(1))
                 for c in re.finditer(r'href="(/auth/select-home-base[^"]+)"', chooser)
                 if hb_id in c.group(1)]
        if not hrefs:
            bad(f"{name}: offered in the chooser", hb_id)
            continue
        u1, b1 = get(op, ALS + hrefs[0])
        act = re.search(r'<form[^>]+action="([^"]+)"', b1)
        if not act:
            bad(f"{name}: shows a sign-in form")
            continue
        _, b2 = post(op, html.unescape(act.group(1)),
                     {"username": user, "password": pw, "credentialId": ""}, referer=u1)
        if "Failed to exchange" in b2:
            bad(f"{name}: token exchange succeeds",
                "401 from the home base — client secret mismatch")
        elif "sessionToken" in b2:
            ok(f"{name}: a reader can sign in through it")
        else:
            bad(f"{name}: token exchange succeeds",
                re.sub(r"<[^>]+>", "", b2)[:60].strip())


def form_fields(body: str) -> dict[str, str]:
    return dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', body))


def exhaust_meter(op, articles: list[str]) -> str:
    """Read the free allowance, then return the body of the gated article."""
    for a in articles[:3]:
        get(op, a)
    _, body = get(op, articles[3])
    return body


def sign_in(op, gated_body: str, user: str, pw: str) -> bool:
    """Follow the gate's own login link all the way to a publisher session."""
    m = re.search(r'href="([^"]*newshare_login=1[^"]*)"', gated_body)
    if not m:
        bad("gate offers a login link")
        return False
    url, body = get(op, html.unescape(m.group(1)))

    if "/auth/select-home-base" not in body:
        bad("gate button reaches the chooser", url[:44])
        return False
    ok("gate button reaches the chooser")

    href = None
    for cand in re.finditer(r'href="(/auth/select-home-base[^"]+)"', body):
        if HOME_BASE in cand.group(1):
            href = html.unescape(cand.group(1))
            break
    if not href:
        bad("chooser lists the home base")
        return False

    url, body = get(op, ALS + href)
    if "Sign in to your account" not in body:
        bad("home base shows a sign-in form", url[:50])
        return False
    ok("home base shows a sign-in form")

    action = re.search(r'<form[^>]+action="([^"]+)"', body)
    if not action:
        bad("sign-in form is usable")
        return False
    url2, body2 = post(op, html.unescape(action.group(1)),
                       {"username": user, "password": pw, "credentialId": ""},
                       referer=url)

    fields = form_fields(body2)
    if "sessionToken" not in fields:
        bad("session token issued", body2[:60])
        return False

    header = json.loads(base64.urlsafe_b64decode(
        fields["sessionToken"].split(".")[0] + "=="))
    claims = json.loads(base64.urlsafe_b64decode(
        fields["sessionToken"].split(".")[1] + "=="))
    if header.get("kid"):
        ok("token carries a key id", header["kid"])
    else:
        bad("token carries a key id", "publishers cannot verify it")
    if claims.get("networkGroupId"):
        ok("token carries a subscription tier", str(claims["networkGroupId"]))
    else:
        bad("token carries a subscription tier", "reader would stay gated")

    handoff = re.search(r'action="([^"]+)"', body2).group(1)
    _, body3 = post(op, handoff, fields, referer=url2)
    if any(w in body3.lower() for w in ("no route", "invalid_state", "jwt_validation")):
        bad("publisher accepted the hand-off", body3[:70])
        return False
    ok("publisher accepted the hand-off")
    return True


def main() -> int:
    user, pw = credentials()
    op, jar = session()

    print("\nEVERY HOME BASE, NOT JUST THE FIRST")
    every_home_base_works("barharbor")

    print("\nTHE WHOLE SITE IS FOR SALE, NOT JUST THE SEEDED FEW")
    archive_is_metered("barharbor", "Bar Harbor")
    archive_is_metered("northberkshire", "North Berkshire")
    archive_is_metered("wesmc", "West End Sentinel")

    print("\nPUBLISHER A — BAR HARBOR")
    a_articles = priced_articles("barharbor")
    if len(a_articles) < 4:
        bad("four priced articles available", str(len(a_articles)))
        return 1
    body = exhaust_meter(op, a_articles)
    if "newshare-login-btn" in body:
        ok("fourth article is gated")
    else:
        bad("fourth article is gated", "meter not enforced")
        return 1

    if not sign_in(op, body, user, pw):
        return 1

    cookies = [c.name for c in jar if "barharbor" in c.domain]
    if any(c.startswith("wordpress_logged_in") for c in cookies):
        ok("publisher session established")
    else:
        bad("publisher session established", str(cookies[:3]))

    _, after = get(op, a_articles[3])
    if "newshare-login-btn" not in after:
        ok("gated article now served in full")
    else:
        bad("gated article now served in full")

    print("\nPUBLISHER B — NORTH BERKSHIRE")
    b_articles = priced_articles("northberkshire")
    body_b = exhaust_meter(op, b_articles)
    if "newshare-login-btn" not in body_b:
        ok("recognised immediately, never gated")
    else:
        m = re.search(r'href="([^"]*newshare_login=1[^"]*)"', body_b)
        url, page = get(op, html.unescape(m.group(1)))
        if "Sign in to your account" in page:
            bad("crossed without a second password", "was asked again")
        else:
            ok("crossed without a second password")
        if "/auth/select-home-base" in page:
            bad("crossed without choosing a home base again")
        else:
            ok("crossed without choosing a home base again")
        fields = form_fields(page)
        if "sessionToken" in fields:
            post(op, re.search(r'action="([^"]+)"', page).group(1), fields, referer=url)
        _, after_b = get(op, b_articles[3])
        if "newshare-login-btn" not in after_b:
            ok("second publisher's article served in full")
        else:
            bad("second publisher's article served in full")

    # The privacy claim: the same reader, a different opaque id at each site.
    ids = {}
    for host in PUBLISHERS:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", f"{host}@svaha.com",
             "export PATH=~/bin:$PATH; cd ~/public_html; "
             "for u in $(wp user list --field=ID); do "
             "v=$(wp user meta get $u newshare_network_user_id 2>/dev/null); "
             '[ -n "$v" ] && echo "$v"; done'],
            capture_output=True, text=True, timeout=90).stdout.split()
        if out:
            ids[host] = out[-1]

    print("\nTHE PRIVACY CLAIM")
    if len(ids) == 2 and len(set(ids.values())) == 2:
        ok("a different opaque id at each publisher")
        for h, v in ids.items():
            print(f"      {h:<16} {v}")
    else:
        bad("a different opaque id at each publisher", str(ids))

    print()
    print(f"  {len(PASS)} passed, {len(FAIL)} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
