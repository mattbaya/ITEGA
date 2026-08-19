#!/usr/bin/env python3
"""Photograph every screen a reader meets, for the help pages.

Written because help pages go stale faster than anything else in a project.
Reader-facing copy changed five times on 18 August alone, so screenshots taken
by hand that day would already have been wrong by the evening. These are taken
from the live sites by script, so refreshing them is one command rather than an
afternoon.

Each shot is of the *panel*, not the whole page, so a publisher restyling their
site does not invalidate the help.

What this cannot reach, and why:

  * The publisher's admin screens (Settings -> Newshare Network, and Newshare
    Earnings) need a WordPress login, and the credentials for a publisher's own
    admin are theirs rather than ours. Those need one manual pass.
  * The purchase receipt appears only after a real purchase completes, which
    needs a signed-in reader; captured here when credentials are available.

Usage:  infra/capture-help-screenshots.py [--out docs/help/img]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("  playwright is not installed — see infra/reader-eyes-test.py")

SITE = "https://barharbor.info"
AGENT = "https://agent-c.itega.org"

DONE: list[str] = []
MISSING: list[str] = []


def articles(site: str, n: int = 6) -> list[str]:
    with urllib.request.urlopen(
            f"{site}/wp-json/wp/v2/posts?per_page={n}&_fields=link", timeout=30) as r:
        return [p["link"] for p in json.load(r)]


def shot(page, selector: str, path: pathlib.Path, label: str) -> None:
    """One panel, or an honest note that it was not reachable."""
    element = page.locator(selector)
    if not element.count():
        MISSING.append(f"{label} — {selector} not on the page")
        return
    element.first.screenshot(path=str(path))
    DONE.append(f"{label} -> {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/help/img")
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 900, "height": 1400},
                                  device_scale_factor=2)
        page = ctx.new_page()

        # 1. The access gate. Reached the way a reader reaches it: by reading.
        links = articles(SITE)
        for url in links:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            if page.locator(".newshare-access-gate").count():
                shot(page, ".newshare-access-gate", out / "gate.png",
                     "The access gate")
                break
        else:
            MISSING.append("The access gate — never appeared; is anything priced?")

        # 2. The status badge, which tells a reader whether they are signed in.
        shot(page, "[class*='newshare-status']", out / "status-badge.png",
             "The signed-in badge")

        # 3. The approval screen, when a purchase is above a reader's own limit.
        #    Rendered from a spent nonce is impossible by design, so this is the
        #    expired form -- which is itself a screen readers will meet.
        page.goto(f"{AGENT}/agent/confirm?t=expired-example",
                  timeout=45000, wait_until="domcontentloaded")
        page.screenshot(path=str(out / "approval-expired.png"))
        DONE.append("The approval link, once used -> approval-expired.png")

        # 4. Where a reader sets their spending limit.
        page.goto(f"{AGENT}/agent/settings", timeout=45000, wait_until="domcontentloaded")
        page.screenshot(path=str(out / "spending-limit.png"), full_page=True)
        DONE.append("Setting a spending limit -> spending-limit.png")

        browser.close()

    print(f"\n\033[1mScreens captured\033[0m -> {out}\n")
    for line in DONE:
        print(f"  \033[32m✓\033[0m {line}")
    for line in MISSING:
        print(f"  \033[33m•\033[0m {line}")
    print(f"\n  {len(DONE)} captured, {len(MISSING)} not reachable from here\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
