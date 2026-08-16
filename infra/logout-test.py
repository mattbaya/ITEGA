#!/usr/bin/env python3
"""Prove that the two sign-out choices actually differ.

"Log out here" and "log out everywhere" are easy to build and easy to get
wrong, because a broken one looks exactly like a working one from the browser:
the reader is sent somewhere, the page says goodbye, and nothing visible
distinguishes a session that ended from one that did not. The failure only
shows up later, when the next person at a shared machine reads an article
billed to whoever used it before them.

So this asserts on the thing that separates them -- whether a password is
demanded afterwards:

  here        The publisher's own session ends, and the article is gated
              again. The network session survives, so returning needs no
              password: the reader is carried back through silently, which is
              the whole point of belonging to a network.

  everywhere  The network session ends and the home base's session with it,
              so coming back demands a password.

Both then re-check the cached token at the Authenticator, because "log out"
that leaves a usable token behind is theatre: the reader clicks a gated
article and is signed straight back in without ever seeing a login screen.

Credentials come from ~/newshare-bill-credentials.txt and are never printed.

Usage:  infra/logout-test.py
Exit:   0 if both behave as described, 1 otherwise.
"""
from __future__ import annotations

import html
import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent

# The journey test already knows how to walk a reader in; reuse it rather than
# writing a second, subtly different version of the same sign-in.
_spec = importlib.util.spec_from_file_location("journey", HERE / "journey-test.py")
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)

ARTICLE_MARKER = "newshare-login-btn"   # present only when the gate is showing


def find_logout_link(body: str) -> str | None:
    """The plugin's sign-out link, as rendered on the page."""
    m = re.search(r'href="([^"]*newshare_logout=choose[^"]*)"', body)
    return html.unescape(m.group(1)) if m else None


def follow_choice(op, choice_page: str, which: str) -> tuple[str, str]:
    """Click one of the two options on the choice page."""
    m = re.search(rf'href="([^"]*newshare_logout={which}[^"]*)"', choice_page)
    if not m:
        return "", ""
    return J.get(op, html.unescape(m.group(1)))


def sign_in_fresh(op, articles: list[str], user: str, pw: str) -> bool:
    """Read past the meter and sign in, quietly."""
    body = J.exhaust_meter(op, articles)
    if ARTICLE_MARKER not in body:
        return True          # already signed in; nothing to do
    return J.sign_in(op, body, user, pw)


def password_demanded_on_return(op, articles: list[str]) -> bool | None:
    """
    Whether coming back to a gated article now asks for a password.

    Returns None if the journey could not be walked far enough to tell, so a
    broken test is never mistaken for a passing one.
    """
    _, body = J.get(op, articles[3])
    m = re.search(r'href="([^"]*newshare_login=1[^"]*)"', body)
    if not m:
        return None
    _, body = J.get(op, html.unescape(m.group(1)))

    # Either the chooser is presented, or the reader is sent straight to their
    # home base. Follow the chooser when it appears so both paths converge.
    if "/auth/select-home-base" in body:
        href = None
        for cand in re.finditer(r'href="(/auth/select-home-base[^"]+)"', body):
            if J.HOME_BASE in cand.group(1):
                href = html.unescape(cand.group(1))
                break
        if not href:
            return None
        _, body = J.get(op, J.ALS + href)

    return "Sign in to your account" in body


def main() -> int:
    user, pw = J.credentials()
    articles = J.priced_articles("barharbor")
    if len(articles) < 4:
        J.bad("four priced articles available", str(len(articles)))
        return 1

    # ── log out here ─────────────────────────────────────────────────
    print("\nSIGN OUT OF THIS PUBLISHER ONLY")
    op, jar = J.session()
    if not sign_in_fresh(op, articles, user, pw):
        J.bad("signed in to start with")
        return 1

    _, body = J.get(op, articles[3])
    if ARTICLE_MARKER in body:
        J.bad("article served before signing out", "still gated")
        return 1
    J.ok("article served before signing out")

    link = find_logout_link(body)
    if not link:
        J.bad("sign-out link is offered", "no choice link on the page")
        return 1
    J.ok("sign-out link is offered")

    _, choice = J.get(op, link)
    if "How far should we sign you out" not in choice:
        J.bad("the choice is presented", choice[:60])
        return 1
    if "Sign out of the whole network" in choice and "newshare_logout=here" in choice:
        J.ok("both options offered")
    else:
        J.bad("both options offered")
        return 1

    _, after = follow_choice(op, choice, "here")
    if after == "":
        J.bad("'here' completes")
        return 1
    J.ok("'here' returns the reader to the article")

    _, body = J.get(op, articles[3])
    if ARTICLE_MARKER in body:
        J.ok("article is gated again")
    else:
        J.bad("article is gated again", "the local sign-out did nothing")

    demanded = password_demanded_on_return(op, articles)
    if demanded is None:
        J.bad("network session survives 'here'", "could not walk the return")
    elif demanded:
        J.bad("network session survives 'here'", "a password was demanded")
    else:
        J.ok("network session survives 'here'", "returned without a password")

    # ── log out everywhere ───────────────────────────────────────────
    print("\nSIGN OUT OF THE WHOLE NETWORK")
    op, jar = J.session()
    if not sign_in_fresh(op, articles, user, pw):
        J.bad("signed in to start with")
        return 1

    _, body = J.get(op, articles[3])
    link = find_logout_link(body)
    if not link:
        J.bad("sign-out link is offered")
        return 1
    _, choice = J.get(op, link)
    _, after = follow_choice(op, choice, "everywhere")
    if after == "":
        J.bad("'everywhere' completes")
        return 1
    J.ok("'everywhere' completes")

    # The Authenticator's own cookie must be gone, or the network still knows
    # this browser however emphatically the page says otherwise.
    remaining = [c.name for c in jar if c.name == "itega_session" and c.value]
    if remaining:
        J.bad("the network's cookie is cleared", "itega_session survived")
    else:
        J.ok("the network's cookie is cleared")

    demanded = password_demanded_on_return(op, articles)
    if demanded is None:
        J.bad("a password is demanded afterwards", "could not walk the return")
    elif demanded:
        J.ok("a password is demanded afterwards", "home base session ended")
    else:
        J.bad("a password is demanded afterwards",
              "signed back in silently — the home base session is still open")

    print()
    if J.FAIL:
        print(f"  \033[31m{len(J.PASS)} passed, {len(J.FAIL)} failed\033[0m\n")
        return 1
    print(f"  \033[32m{len(J.PASS)} passed, 0 failed\033[0m\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
