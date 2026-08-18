#!/usr/bin/env python3
"""Prove demo mode leaves no trace of the plugin.

A publisher hosting this on a live site was promised their ordinary readers
would see nothing of it. This checks that claim, rather than checking the
handful of things we happen to remember building.

That distinction is the whole point of this file. Demo mode was tested before
Greylock Glass installed the plugin, and it passed: the check grepped for the
access gate and the status badge, found neither, and reported success. It was
looking for two class names. Meanwhile every page carried

    /wp-content/plugins/newshare-network/assets/css/newshare-login.css

which is not a gate, is not a badge, and is exactly the sort of thing "no
trace" is supposed to exclude. So this asserts on the property: fetch a real
page as an ordinary reader and fail if the word "newshare" appears anywhere
in it at all.

Runs against our own sites by toggling demo mode on, checking, and restoring.
"""
import re
import subprocess
import sys
import urllib.request

# host, wp directory, public URL
SITES = [
    ("barharbor@svaha.com", "public_html", "https://barharbor.info/"),
    ("northberkshire@svaha.com", "public_html", "https://northberkshire.org/"),
    ("northberkshire@svaha.com", "wesmc.org", "https://wesmc.org/"),
]

# Markers only this plugin can emit.
#
# The first draft looked for the bare words "newshare" and "itega", on the
# reasoning that any mention at all is a trace. That is too broad on our own
# demonstration sites, whose page copy genuinely says "the ITEGA / Newshare
# Network pilot" -- editorial content, not plugin output, and no reader would
# be misled by it.
#
# The list below is still the property rather than a sample of it: these cover
# every route by which the plugin can reach a page. Its asset directory, the
# class prefix on everything it renders, the opt-in parameter and cookie, and
# the rights metadata. Adding a new surface means adding it here; a marker
# that leaked before -- the asset path -- is first on the list.
FINGERPRINTS = (
    "wp-content/plugins/newshare-network",   # the leak Greylock exposed
    "newshare-status",                       # the badge
    "newshare-gate",                         # the access gate
    "newshare-login",                        # gate and login styling
    "newshare_demo",                         # opt-in parameter and cookie
    "newshare_page_class",                   # per-article price meta
    "rslstandard.org",                       # rights metadata
)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

passed, failed = [], []


def check(label, ok, detail=""):
    (passed if ok else failed).append(label)
    mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    print(f"  {mark} {label:<46} {detail}")


def wp(host, directory, command):
    out = subprocess.run(
        ["ssh", host, f"cd ~/{directory} && ~/bin/wp {command}"],
        capture_output=True, text=True, timeout=120)
    return out.stdout.strip()


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def article_url(host, directory):
    url = wp(host, directory,
             "post list --post_type=post --post_status=publish "
             "--posts_per_page=1 --field=url")
    return url.splitlines()[-1].strip() if url else ""


print("\nDEMO MODE LEAVES NO TRACE\n" + "=" * 62)

for host, directory, home in SITES:
    name = directory if directory != "public_html" else host.split("@")[0]
    print(f"\n{name}")

    was = wp(host, directory, "option get newshare_demo_mode") or "0"
    key = wp(host, directory, "option get newshare_demo_key") or ""
    article = article_url(host, directory)

    try:
        wp(host, directory, "option update newshare_demo_mode 1")
        wp(host, directory, "option update newshare_demo_key ''")

        for label, url in (("front page", home), ("an article", article)):
            if not url:
                continue
            body = fetch(url)
            hits = sorted({
                m for f in FINGERPRINTS
                for m in re.findall(rf".{{0,40}}{re.escape(f)}.{{0,40}}", body, re.I)
            })
            # Report the first hit, since that is what a person would see.
            check(f"{label}: no fingerprint in the page",
                  not hits,
                  "" if not hits else f"found {len(hits)}: {hits[0].strip()[:60]!r}")
    finally:
        wp(host, directory, f"option update newshare_demo_mode {was}")
        if key:
            wp(host, directory, f"option update newshare_demo_key '{key}'")

    restored = wp(host, directory, "option get newshare_demo_mode") or "0"
    check("demo mode restored", restored == was, f"{restored} (was {was})")

print(f"\n  {len(passed)} passed, {len(failed)} failed\n")
sys.exit(1 if failed else 0)
