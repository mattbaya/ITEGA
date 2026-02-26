#!/usr/bin/env python3
"""
ALS Settlement Service — Weekly batch settlement script.

This is component #4 in the Newshare four-party architecture.  It runs as a
periodic batch job (typically weekly via cron) and performs the financial
reconciliation between home bases (who owe money) and publishers (who earn
money), with ITEGA taking a small governance fee.

Wholesale-retail pricing model
------------------------------
Each content-access event has two pricing components:

  1. **pageClass** -- a wholesale price tier set by the publisher when
     tagging content (e.g. 0.01 for a free article, 0.50 for premium).
  2. **markupRatio** -- a retail multiplier set by the home base, reflecting
     the subscription plan the user has chosen.

The **wholesale value** of an event is: ``pageClass * markupRatio``.

Money flow
----------
::

    Home Base (debit)  -->  Publisher (credit)
                        |
                        +--> ITEGA fee (governance overhead)

- Home bases are debited the full wholesale total for their users' access.
- Publishers are credited the wholesale total MINUS the ITEGA fee.
- The ITEGA fee is computed as a percentage of the publisher's wholesale
  total (default 1.5%, configurable via ``itega_fee_pct``).

Balance invariant
-----------------
For any settlement period, the following must hold:

    SUM(home_base_debits) == SUM(publisher_credits) + ITEGA_fee

More precisely: the raw wholesale totals from the home-base side must equal
the raw wholesale totals from the publisher side (before fee deduction),
because every event is attributed to exactly one home base AND one publisher.
The script validates this invariant before writing settlement results.

Usage
-----
    # Automatic weekly period (previous Monday 00:00 UTC to this Monday 00:00 UTC)
    python settle.py --period=weekly

    # Explicit date range
    python settle.py --start=2026-03-01 --end=2026-03-07

Cron entry (runs 2 AM UTC every Sunday):
    0 2 * * 0  cd /opt/als-settlement && python settle.py --period=weekly

Exit codes:
    0  -- settlement completed successfully
    1  -- validation error (debits != credits)
    2  -- database or I/O error
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dateutil import parser as dateparser

from config import settings

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("als-settlement")

# ── Decimal helpers ───────────────────────────────────────────────────
#
# All monetary calculations use Python's ``Decimal`` type to avoid
# floating-point rounding errors.  Values are quantized to 4 decimal
# places (matching the NUMERIC(12,4) columns in the settlement DB).

FOUR_PLACES = Decimal("0.0001")


def dec(value: Any) -> Decimal:
    """Convert a value to Decimal with 4 decimal places (banker-safe)."""
    return Decimal(str(value)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


# ── Period resolution ─────────────────────────────────────────────────
#
# Determines the time window for the settlement batch.  The default
# "weekly" mode settles the most recent complete ISO week (Monday to
# Monday), ensuring no partial-day edge effects.

def resolve_period(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """
    Return (period_start, period_end) as timezone-aware UTC datetimes.

    For --period=weekly the window is the most recent full ISO week
    (Monday to Monday).
    """
    if args.period == "weekly":
        now = datetime.now(timezone.utc)
        # Monday of current week
        this_monday = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=now.weekday())
        period_end = this_monday
        period_start = this_monday - timedelta(weeks=1)
        return period_start, period_end

    if args.start and args.end:
        start = dateparser.parse(args.start)
        end = dateparser.parse(args.end)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return start, end

    logger.error("Provide --period=weekly OR both --start and --end")
    sys.exit(2)


# ── Database helpers ──────────────────────────────────────────────────
#
# Two separate database connections are used:
#   1. als_logs (read-only)     -- source of access_events data
#   2. als_settlement (read-write) -- destination for settlement results

def connect_logs() -> psycopg2.extensions.connection:
    """
    Open a read-only connection to the als_logs database.

    Uses REPEATABLE READ isolation to ensure a consistent snapshot of the
    access_events data throughout the settlement batch.  Without this,
    concurrent inserts during the batch could cause the home-base and
    publisher aggregate queries to see different data, violating the
    balance invariant (total debits must equal total credits).
    """
    conn = psycopg2.connect(settings.als_logs_database_url)
    conn.set_session(
        readonly=True,
        isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ,
        autocommit=False,
    )
    return conn


def connect_settlement() -> psycopg2.extensions.connection:
    """
    Open a read-write connection to the als_settlement database.

    Uses the default READ COMMITTED isolation, which is sufficient for
    the settlement writes (only one batch job runs at a time).
    """
    conn = psycopg2.connect(settings.als_settlement_database_url)
    conn.set_session(autocommit=False)
    return conn


def ensure_settlement_schema(conn: psycopg2.extensions.connection) -> None:
    """
    Create settlement tables if they do not exist.

    Three tables:
      - settlement_runs: one row per batch execution, with period, totals,
        and the ITEGA fee amount.
      - home_base_debits: one row per home base per settlement run.
      - publisher_credits: one row per publisher per settlement run (net of fee).
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settlement_runs (
                id              SERIAL          PRIMARY KEY,
                period_start    TIMESTAMPTZ     NOT NULL,
                period_end      TIMESTAMPTZ     NOT NULL,
                status          VARCHAR(32)     NOT NULL DEFAULT 'pending',
                total_events    INTEGER         NOT NULL DEFAULT 0,
                total_wholesale NUMERIC(12,4)   NOT NULL DEFAULT 0,
                itega_fee_pct   NUMERIC(4,4)    NOT NULL DEFAULT 0.0150,
                itega_fee_amt   NUMERIC(12,4)   NOT NULL DEFAULT 0,
                created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS home_base_debits (
                id              SERIAL          PRIMARY KEY,
                settlement_id   INTEGER         NOT NULL
                    REFERENCES settlement_runs(id) ON DELETE CASCADE,
                home_base_id    VARCHAR(32)     NOT NULL,
                total_events    INTEGER         NOT NULL DEFAULT 0,
                total_wholesale NUMERIC(12,4)   NOT NULL DEFAULT 0,
                amount_owed     NUMERIC(12,4)   NOT NULL DEFAULT 0
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS publisher_credits (
                id              SERIAL          PRIMARY KEY,
                settlement_id   INTEGER         NOT NULL
                    REFERENCES settlement_runs(id) ON DELETE CASCADE,
                pub_mbr_id      VARCHAR(32)     NOT NULL,
                total_events    INTEGER         NOT NULL DEFAULT 0,
                total_wholesale NUMERIC(12,4)   NOT NULL DEFAULT 0,
                amount_earned   NUMERIC(12,4)   NOT NULL DEFAULT 0
            );
        """)
    conn.commit()
    logger.info("Settlement schema verified")


# ── Phase 1: Aggregate ────────────────────────────────────────────────
#
# Read the access_events table and compute per-home-base and per-publisher
# wholesale totals.  Only ``content_access`` events are included in
# settlement (authentication, logout, etc. are non-metered).
#
# IMPORTANT: The logs connection uses REPEATABLE READ isolation so that
# both queries below see the same snapshot of access_events, even if new
# events are being inserted concurrently.

def fetch_aggregates(
    conn: psycopg2.extensions.connection,
    period_start: datetime,
    period_end: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Query the access_events table and return home-base debits and
    publisher credits as lists of dicts.

    Wholesale value = SUM(page_class * markup_ratio).

    Both queries run within the same REPEATABLE READ transaction to
    guarantee consistent aggregates.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Home base debits: one row per home_base_id, summing the
        # wholesale value of all content_access events in the period.
        cur.execute(
            """
            SELECT home_base_id,
                   COUNT(*)::int                          AS total_events,
                   COALESCE(SUM(page_class * markup_ratio), 0) AS total_wholesale
              FROM access_events
             WHERE timestamp >= %s
               AND timestamp <  %s
               AND event_type = 'content_access'
             GROUP BY home_base_id
             ORDER BY home_base_id
            """,
            (period_start, period_end),
        )
        hb_rows = [dict(r) for r in cur.fetchall()]

        # Publisher credits: one row per pub_mbr_id, same aggregation.
        # The totals from hb_rows and pub_rows MUST be equal (validated
        # by validate_balance) because every event belongs to exactly
        # one home base and one publisher.
        cur.execute(
            """
            SELECT pub_mbr_id,
                   COUNT(*)::int                          AS total_events,
                   COALESCE(SUM(page_class * markup_ratio), 0) AS total_wholesale
              FROM access_events
             WHERE timestamp >= %s
               AND timestamp <  %s
               AND event_type = 'content_access'
             GROUP BY pub_mbr_id
             ORDER BY pub_mbr_id
            """,
            (period_start, period_end),
        )
        pub_rows = [dict(r) for r in cur.fetchall()]

    return hb_rows, pub_rows


# ── Phase 2: Validate balance ─────────────────────────────────────────

def validate_balance(
    hb_rows: list[dict[str, Any]],
    pub_rows: list[dict[str, Any]],
) -> None:
    """
    Verify that the sum of home-base wholesale totals equals the sum of
    publisher wholesale totals.  This is a fundamental accounting invariant:

        SUM(hb debits) == SUM(pub credits, before fee deduction)

    If the totals differ, it indicates a data integrity problem (e.g.
    an event with a missing home_base_id or pub_mbr_id).  The script
    aborts with exit code 1 in this case.
    """
    total_hb = sum(dec(r["total_wholesale"]) for r in hb_rows)
    total_pub = sum(dec(r["total_wholesale"]) for r in pub_rows)

    if total_hb != total_pub:
        logger.error(
            "BALANCE MISMATCH: home-base total=%s, publisher total=%s",
            total_hb,
            total_pub,
        )
        sys.exit(1)

    logger.info("Balance verified: debits == credits == %s", total_hb)


# ── Phase 3: Insert settlement records ────────────────────────────────

def insert_settlement(
    conn: psycopg2.extensions.connection,
    period_start: datetime,
    period_end: datetime,
    hb_rows: list[dict[str, Any]],
    pub_rows: list[dict[str, Any]],
    itega_fee_pct: Decimal,
) -> int:
    """
    Insert a settlement_run and its associated debit/credit rows.

    The ITEGA fee is calculated as follows:
      - itega_fee_amt = total_wholesale * itega_fee_pct
      - Each publisher's earned amount = their wholesale - their share of fee
      - Home bases owe the FULL wholesale amount (fee is not added to debit;
        it is subtracted from the publisher credit side).

    Returns the settlement_run id.
    """
    total_events = sum(r["total_events"] for r in hb_rows)
    total_wholesale = sum(dec(r["total_wholesale"]) for r in hb_rows)
    itega_fee_amt = (total_wholesale * itega_fee_pct).quantize(
        FOUR_PLACES, rounding=ROUND_HALF_UP
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO settlement_runs
                (period_start, period_end, status, total_events,
                 total_wholesale, itega_fee_pct, itega_fee_amt)
            VALUES (%s, %s, 'completed', %s, %s, %s, %s)
            RETURNING id
            """,
            (
                period_start,
                period_end,
                total_events,
                total_wholesale,
                itega_fee_pct,
                itega_fee_amt,
            ),
        )
        settlement_id: int = cur.fetchone()[0]

        # Home base debits
        for r in hb_rows:
            wholesale = dec(r["total_wholesale"])
            # The home base owes the full wholesale amount (the ITEGA fee
            # is deducted from the publisher side, not added to the debit).
            cur.execute(
                """
                INSERT INTO home_base_debits
                    (settlement_id, home_base_id, total_events,
                     total_wholesale, amount_owed)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    settlement_id,
                    r["home_base_id"],
                    r["total_events"],
                    wholesale,
                    wholesale,
                ),
            )

        # Publisher credits (net of ITEGA fee)
        for r in pub_rows:
            wholesale = dec(r["total_wholesale"])
            fee = (wholesale * itega_fee_pct).quantize(
                FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            earned = wholesale - fee
            cur.execute(
                """
                INSERT INTO publisher_credits
                    (settlement_id, pub_mbr_id, total_events,
                     total_wholesale, amount_earned)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    settlement_id,
                    r["pub_mbr_id"],
                    r["total_events"],
                    wholesale,
                    earned,
                ),
            )

    conn.commit()
    logger.info("Settlement run #%d written to database", settlement_id)
    return settlement_id


# ── Phase 4: Report generation ────────────────────────────────────────
#
# Generates three types of output files:
#   1. JSON summary — machine-readable settlement overview.
#   2. Per-home-base CSVs — itemised event detail (home bases see full
#      clickstream for their own users).
#   3. Per-publisher CSVs — aggregated by home_base_id only (publishers
#      NEVER see individual user data; this is a critical privacy rule).

def generate_reports(
    settlement_id: int,
    period_start: datetime,
    period_end: datetime,
    hb_rows: list[dict[str, Any]],
    pub_rows: list[dict[str, Any]],
    itega_fee_pct: Decimal,
    logs_conn: psycopg2.extensions.connection,
) -> None:
    """
    Write settlement reports to disk:
      - JSON summary
      - Per-home-base CSV (itemised events)
      - Per-publisher CSV (aggregated by home_base_id)
    """
    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    date_label = period_start.strftime("%Y-%m-%d")
    total_wholesale = sum(dec(r["total_wholesale"]) for r in hb_rows)
    itega_fee_amt = (total_wholesale * itega_fee_pct).quantize(
        FOUR_PLACES, rounding=ROUND_HALF_UP
    )

    # ── JSON summary ──────────────────────────────────────────────────
    summary = {
        "settlement_id": settlement_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_events": sum(r["total_events"] for r in hb_rows),
        "total_wholesale": str(total_wholesale),
        "itega_fee_pct": str(itega_fee_pct),
        "itega_fee_amt": str(itega_fee_amt),
        "home_base_debits": [
            {
                "home_base_id": r["home_base_id"],
                "total_events": r["total_events"],
                "total_wholesale": str(dec(r["total_wholesale"])),
                "amount_owed": str(dec(r["total_wholesale"])),
            }
            for r in hb_rows
        ],
        "publisher_credits": [
            {
                "pub_mbr_id": r["pub_mbr_id"],
                "total_events": r["total_events"],
                "total_wholesale": str(dec(r["total_wholesale"])),
                "amount_earned": str(
                    dec(r["total_wholesale"])
                    - (dec(r["total_wholesale"]) * itega_fee_pct).quantize(
                        FOUR_PLACES, rounding=ROUND_HALF_UP
                    )
                ),
            }
            for r in pub_rows
        ],
    }

    summary_path = reports_dir / f"settlement-{date_label}.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info("Wrote %s", summary_path)

    # ── Per-home-base CSVs (itemised) ─────────────────────────────────
    for hb in hb_rows:
        hb_id = hb["home_base_id"]
        csv_path = reports_dir / f"home-base-{hb_id}-{date_label}.csv"

        with logs_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT timestamp, network_user_id, pub_mbr_id,
                       resource_id, page_class, service_class,
                       markup_ratio, event_type, session_id
                  FROM access_events
                 WHERE home_base_id = %s
                   AND timestamp >= %s
                   AND timestamp <  %s
                   AND event_type = 'content_access'
                 ORDER BY timestamp
                """,
                (hb_id, period_start, period_end),
            )
            events = cur.fetchall()

        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "network_user_id",
                "pub_mbr_id",
                "resource_id",
                "page_class",
                "service_class",
                "markup_ratio",
                "wholesale",
                "event_type",
                "session_id",
            ])
            for e in events:
                wholesale = dec(e["page_class"]) * dec(e["markup_ratio"])
                writer.writerow([
                    e["timestamp"].isoformat(),
                    e["network_user_id"],
                    e["pub_mbr_id"],
                    e["resource_id"],
                    e["page_class"],
                    e["service_class"],
                    e["markup_ratio"],
                    str(wholesale),
                    e["event_type"],
                    e["session_id"],
                ])

        logger.info("Wrote %s (%d events)", csv_path, len(events))

    # ── Per-publisher CSVs (aggregated — NO individual user data) ─────
    for pub in pub_rows:
        pub_id = pub["pub_mbr_id"]
        csv_path = reports_dir / f"publisher-{pub_id}-{date_label}.csv"

        with logs_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT home_base_id,
                       COUNT(*)::int                          AS total_events,
                       COALESCE(SUM(page_class), 0)           AS total_page_class,
                       COALESCE(SUM(page_class * markup_ratio), 0) AS total_wholesale
                  FROM access_events
                 WHERE pub_mbr_id = %s
                   AND timestamp >= %s
                   AND timestamp <  %s
                   AND event_type = 'content_access'
                 GROUP BY home_base_id
                 ORDER BY home_base_id
                """,
                (pub_id, period_start, period_end),
            )
            agg_rows = cur.fetchall()

        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "home_base_id",
                "total_events",
                "total_page_class",
                "total_wholesale",
                "itega_fee",
                "amount_earned",
            ])
            for a in agg_rows:
                ws = dec(a["total_wholesale"])
                fee = (ws * itega_fee_pct).quantize(
                    FOUR_PLACES, rounding=ROUND_HALF_UP
                )
                writer.writerow([
                    a["home_base_id"],
                    a["total_events"],
                    a["total_page_class"],
                    str(ws),
                    str(fee),
                    str(ws - fee),
                ])

        logger.info("Wrote %s (%d rows)", csv_path, len(agg_rows))


# ── Phase 5: Summary to stdout ────────────────────────────────────────
#
# Print a human-readable summary to stdout for the operator.  This is
# also useful for cron job email notifications.

def print_summary(
    settlement_id: int,
    period_start: datetime,
    period_end: datetime,
    hb_rows: list[dict[str, Any]],
    pub_rows: list[dict[str, Any]],
    itega_fee_pct: Decimal,
) -> None:
    """Print a human-readable settlement summary to stdout."""
    total_events = sum(r["total_events"] for r in hb_rows)
    total_wholesale = sum(dec(r["total_wholesale"]) for r in hb_rows)
    itega_fee_amt = (total_wholesale * itega_fee_pct).quantize(
        FOUR_PLACES, rounding=ROUND_HALF_UP
    )

    print("=" * 64)
    print(f"  SETTLEMENT RUN #{settlement_id}")
    print(f"  Period: {period_start.date()} to {period_end.date()}")
    print("=" * 64)
    print(f"  Total content_access events : {total_events:>10,}")
    print(f"  Total wholesale value        : {total_wholesale:>14}")
    print(f"  ITEGA fee ({itega_fee_pct * 100:.2f}%)           : {itega_fee_amt:>14}")
    print("-" * 64)

    print("\n  HOME BASE DEBITS:")
    for r in hb_rows:
        ws = dec(r["total_wholesale"])
        print(f"    {r['home_base_id']:<16} {r['total_events']:>8,} events  owed: {ws:>12}")

    print("\n  PUBLISHER CREDITS:")
    for r in pub_rows:
        ws = dec(r["total_wholesale"])
        fee = (ws * itega_fee_pct).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        earned = ws - fee
        print(
            f"    {r['pub_mbr_id']:<16} {r['total_events']:>8,} events  "
            f"wholesale: {ws:>10}  fee: {fee:>8}  earned: {earned:>10}"
        )

    print("=" * 64)


# ── Main ──────────────────────────────────────────────────────────────
#
# Orchestrates the five settlement phases:
#   1. Aggregate  -- read access_events and compute per-party totals
#   2. Validate   -- verify the balance invariant (debits == credits)
#   3. Insert     -- write settlement_runs, home_base_debits, publisher_credits
#   4. Report     -- generate JSON summary and CSV detail files
#   5. Summary    -- print human-readable output to stdout

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ALS weekly settlement batch job",
    )
    parser.add_argument(
        "--period",
        choices=["weekly"],
        help="Automatic period selection (weekly = previous full week)",
    )
    parser.add_argument("--start", help="Period start date (ISO-8601)")
    parser.add_argument("--end", help="Period end date (ISO-8601)")
    args = parser.parse_args()

    period_start, period_end = resolve_period(args)
    logger.info(
        "Settlement period: %s to %s",
        period_start.isoformat(),
        period_end.isoformat(),
    )

    itega_fee_pct = dec(settings.itega_fee_pct)

    # ── Connect to databases ──────────────────────────────────────────
    try:
        logs_conn = connect_logs()
        logger.info("Connected to als_logs database")
    except Exception:
        logger.exception("Cannot connect to als_logs database")
        sys.exit(2)

    try:
        settle_conn = connect_settlement()
        logger.info("Connected to als_settlement database")
    except Exception:
        logger.exception("Cannot connect to als_settlement database")
        sys.exit(2)

    try:
        # ── Ensure schema ─────────────────────────────────────────────
        ensure_settlement_schema(settle_conn)

        # ── Fetch aggregates ──────────────────────────────────────────
        hb_rows, pub_rows = fetch_aggregates(logs_conn, period_start, period_end)

        if not hb_rows and not pub_rows:
            logger.warning("No content_access events found for the period")
            print("No events to settle.")
            return

        # ── Validate balance ──────────────────────────────────────────
        validate_balance(hb_rows, pub_rows)

        # ── Write settlement ──────────────────────────────────────────
        settlement_id = insert_settlement(
            settle_conn,
            period_start,
            period_end,
            hb_rows,
            pub_rows,
            itega_fee_pct,
        )

        # ── Generate reports ──────────────────────────────────────────
        generate_reports(
            settlement_id,
            period_start,
            period_end,
            hb_rows,
            pub_rows,
            itega_fee_pct,
            logs_conn,
        )

        # ── Print summary ─────────────────────────────────────────────
        print_summary(
            settlement_id,
            period_start,
            period_end,
            hb_rows,
            pub_rows,
            itega_fee_pct,
        )

        logger.info("Settlement run #%d completed successfully", settlement_id)

    except SystemExit:
        raise
    except Exception:
        logger.exception("Settlement failed")
        try:
            settle_conn.rollback()
        except Exception:
            pass
        sys.exit(2)
    finally:
        logs_conn.close()
        settle_conn.close()


if __name__ == "__main__":
    main()
