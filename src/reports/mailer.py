"""Sending mail, and refusing to send it wrongly.

Two parties get reports and they come from different places, which is the
architecture restated rather than an implementation detail:

**Publishers** are reported to by the exchange. The figures are the ALS's and
the contact details are registered with ITEGA. What they receive is aggregate:
reads and wholesale owed, grouped by home base, with no reader in it and no
retail price — the same constraint the publisher endpoint has always had.

**Readers** are reported to by their home base, and can be by nobody else.
Assembling one means joining pairwise identifiers, which only the home base can
do, and it needs an email address, which the exchange must never hold. ITEGA
reports money; the home base reports people; neither can do the other's job.

The one rule enforced here rather than remembered: a reader's report is a list
of what a person has read, arriving in an inbox. It goes only to an address the
home base already holds for that reader, never to one supplied by a caller.
"""
from __future__ import annotations

import logging
import os
import pathlib
import re
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("newshare.reports")


def credentials() -> tuple[str, str, str]:
    """(username, password, host), from the environment or a local .env.

    Never committed. The .env fallback exists so this runs from a laptop while
    the mailbox is being arranged; in service it comes from the environment.
    """
    user = os.environ.get("EMAIL_USERNAME", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    host = os.environ.get("EMAIL_SERVER", "")
    if user and password and host:
        return user, password, host

    for candidate in (pathlib.Path.cwd() / ".env",
                      pathlib.Path(__file__).resolve().parents[2] / ".env"):
        if not candidate.exists():
            continue
        text = candidate.read_text()
        found = dict(re.findall(r'^([A-Z_-]+)=["\']?([^"\'\n]*)', text, re.M))
        user = user or found.get("EMAIL-USERNAME", "")
        password = password or found.get("EMAIL-PASSWORD", "")
        host = host or found.get("EMAIL-SERVER", "")
        if user and password and host:
            break
    return user, password, host


def send(to: str, subject: str, body: str, dry_run: bool = False) -> bool:
    """One message, plain text, from the network's own address.

    Plain text on purpose. These are short factual statements about somebody's
    money or somebody's reading, they are read on phones, and an HTML version
    would be a second copy of the same sentences to keep in step -- which, on
    the evidence of this project's reader-facing copy, would drift within a
    week.
    """
    user, password, host = credentials()
    if not (user and password and host):
        logger.error("no mail credentials; nothing sent")
        return False

    message = EmailMessage()
    message["From"] = f"Newshare Network <{user}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    if dry_run:
        print(f"--- would send to {to} ---\n{subject}\n\n{body}\n")
        return True

    try:
        with smtplib.SMTP(host, 587, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(user, password)
            smtp.send_message(message)
        logger.info("sent %r to %s", subject, to)
        return True
    except Exception as exc:
        # A failed report is not a failed anything else. Never let this take
        # down the job that generates them.
        logger.error("could not send to %s: %s", to, exc)
        return False


def unsubscribe_footer(where: str) -> str:
    """Every report says how to stop receiving it, in the same place.

    An unsubscribe that does not work, or that a reader cannot find, turns a
    service into a nuisance -- and for reader reports it turns a privacy
    feature into an unwanted record of their reading.
    """
    return (
        "\n\n--\n"
        f"To change how often this arrives, or to stop it, visit {where}.\n"
        "Newshare Network, governed by ITEGA."
    )
