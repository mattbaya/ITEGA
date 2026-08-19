#!/usr/bin/env python3
"""Send publishers and readers the reports they asked for, on the interval they chose.

Both parties can already see their figures — a publisher at Settings → Newshare
Earnings, a reader through their home base — but only by going and looking. A
publisher who receives "this is what you were owed last week" reads it; one who
must remember to open a page does not, and settlement is the claim this network
makes.

Run from cron, once a day:

    src/reports/send_reports.py --kind publisher --interval weekly
    src/reports/send_reports.py --kind reader    --interval weekly

`--dry-run` prints exactly what would be sent and to whom, which is how this was
developed and how it should be checked before any interval is changed.

== Which party sends what, and why it cannot be the other way round ==

**Publisher reports come from the exchange.** The figures are the ALS's, the
contact details are registered with ITEGA, and the content is aggregate: reads
and wholesale owed, grouped by home base. No reader appears in it and no retail
price does, because neither is in the response it is built from.

**Reader reports come from their home base.** Assembling one means joining that
reader's pairwise identifiers, which only their home base can do, and sending it
needs an email address, which the exchange must never hold. The home base is
also the only party that knows what the reader actually paid.

That split is not a deployment convenience. It is the architecture: ITEGA
reports money, the home base reports people.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mailer import send, unsubscribe_footer          # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("newshare.reports")

DISCOVERY = "https://network.itega.org"
LOGGING_SERVICE = "https://als.itega.org/log"

INTERVALS = {"daily": 1, "weekly": 7, "monthly": 30}

# A reader's own preference, on their account at their home base. Absent means
# they have not asked for anything, and nothing is sent -- reports are opt-in,
# because an unrequested list of what somebody has been reading is not a service.
READER_INTERVAL_ATTR = "newshare_report_interval"


def money(amount: float) -> str:
    """Money at the precision this network actually deals in."""
    text = f"{amount:.4f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".00"
    elif len(text.split(".")[1]) == 1:
        text += "0"
    return f"${text}"


def get_json(url: str, api_key: str = "", token: str = "") -> dict | list | None:
    request = urllib.request.Request(url)
    if api_key:
        request.add_header("X-API-Key", api_key)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.warning("could not fetch %s: %s", url.split("?")[0], exc)
        return None


# ── Publishers ────────────────────────────────────────────────────────

def load_contacts(path: str) -> dict[str, str]:
    """Publishing Member ID -> where to write, from a private file.

    Kept out of the registry deliberately. The registry is a public endpoint,
    and a publisher's billing address is not something to publish because it
    was convenient to put it there.
    """
    if not path:
        return {}
    file = pathlib.Path(path)
    if not file.exists():
        logger.warning("no contacts file at %s — nothing to send", path)
        return {}
    try:
        return {str(k): str(v) for k, v in json.loads(file.read_text()).items()}
    except Exception as exc:
        logger.error("could not read %s: %s", path, exc)
        return {}


def publisher_reports(interval: str, api_key: str, dry_run: bool,
                      contacts: dict[str, str]) -> int:
    days = INTERVALS[interval]
    until = datetime.now(timezone.utc)
    since = until - timedelta(days=days)

    publishers = get_json(f"{DISCOVERY}/discovery/publishers") or []
    sent = 0

    for publisher in publishers:
        mbr_id = publisher.get("publishing_member_id", "")
        name = publisher.get("name", mbr_id)
        # Contact details are not in the public registry and must not be: it is
        # served to anyone at network.itega.org. They come from a private file
        # beside the provisioning records, which is ITEGA's own store of who
        # registered what.
        to = contacts.get(mbr_id, "")
        if not to:
            logger.info("%s has no contact address on file — skipped", name)
            continue

        # Z, not isoformat(). A timezone-aware isoformat ends in "+00:00", and
        # a bare + in a query string means a space -- so the service received a
        # timestamp with a hole in it and answered 422.
        report = get_json(
            f"{LOGGING_SERVICE}/report/publisher/{mbr_id}"
            f"?period_start={since:%Y-%m-%dT%H:%M:%SZ}"
            f"&period_end={until:%Y-%m-%dT%H:%M:%SZ}",
            api_key=api_key)
        if report is None:
            continue

        aggregates = report.get("aggregates") or []
        owed = sum(float(a.get("total_wholesale", 0)) for a in aggregates)
        reads = int(report.get("total_events", 0))

        if reads == 0:
            # Silence beats a mail saying nothing happened, weekly, forever.
            logger.info("%s had no network reads this %s — nothing sent", name, interval)
            continue

        lines = [
            f"{name} — what the network owes you",
            "",
            f"{money(owed)} for {reads:,} reads, {since:%-d %B} to {until:%-d %B}.",
            "",
            "By the organisation each reader has their account with:",
        ]
        for a in sorted(aggregates, key=lambda x: -float(x.get("total_wholesale", 0))):
            lines.append(f"  {a.get('home_base_id','?'):<12} "
                         f"{int(a.get('total_events',0)):>6,} reads   "
                         f"{money(float(a.get('total_wholesale',0)))}")
        lines += [
            "",
            "These are wholesale figures: what you asked and are owed. What each",
            "reader paid also includes their own provider's margin, which is",
            "between them and it.",
            "",
            "Individual readers are not listed here and cannot be. Your site",
            "receives a different opaque identifier for each one at each",
            "publication, so there is nobody in these totals to name.",
        ]
        body = "\n".join(lines) + unsubscribe_footer(
            "Settings → Newshare Earnings on your own site")

        if send(to, f"Newshare: {money(owed)} owed to {name} this {interval[:-2]}",
                body, dry_run=dry_run):
            sent += 1

    return sent


# ── Readers ───────────────────────────────────────────────────────────

def reader_reports(interval: str, agent_url: str, dry_run: bool) -> int:
    """Ask a home base's own agent to report to its own readers.

    Deliberately thin. This process does not hold reader email addresses, does
    not resolve identifiers, and could not assemble one of these reports if it
    tried -- it asks the only party that can, and that party decides who has
    opted in.
    """
    result = get_json(f"{agent_url}/agent/reports/due?interval={interval}")
    if result is None:
        logger.warning("agent at %s did not answer", agent_url)
        return 0
    due = result.get("due", [])
    logger.info("%s has %d reader(s) due a %s report", agent_url, len(due), interval)
    if dry_run:
        for reader in due:
            print(f"--- would send to a reader of {result.get('homeBaseId','?')} ---")
            print(reader.get("preview", "(no preview)"), "\n")
        return len(due)
    return int(result.get("sent", 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["publisher", "reader"], required=True)
    parser.add_argument("--interval", choices=sorted(INTERVALS), default="weekly")
    parser.add_argument("--api-key", default="", help="logging service key, for publisher reports")
    parser.add_argument("--agent-url", default="https://agent-c.itega.org",
                        help="a home base's Retail Agent, for reader reports")
    parser.add_argument("--contacts", default="/opt/newshare/infra/vps2/secrets/publisher-contacts.json",
                        help="private map of Publishing Member ID to email address")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be sent, to whom, and send nothing")
    args = parser.parse_args()

    if args.kind == "publisher":
        sent = publisher_reports(args.interval, args.api_key, args.dry_run,
                                 load_contacts(args.contacts))
    else:
        sent = reader_reports(args.interval, args.agent_url, args.dry_run)

    print(f"  {sent} {args.kind} report(s) {'previewed' if args.dry_run else 'sent'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
