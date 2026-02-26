-- ============================================================
-- Migration 003: ALS Settlement
-- Target database: als_settlement (VPS 2)
-- ============================================================

BEGIN;

-- ------------------------------------------------
-- Settlement runs
-- Each row represents one billing cycle (typically monthly).
-- The settlement engine reads from als_logs.access_events,
-- aggregates totals, and writes results here.
-- ------------------------------------------------
CREATE TABLE settlement_runs (
    id              SERIAL PRIMARY KEY,
    period_start    TIMESTAMPTZ NOT NULL,
    period_end      TIMESTAMPTZ NOT NULL,
    status          VARCHAR(32) DEFAULT 'pending',
    total_events    INTEGER DEFAULT 0,
    total_wholesale NUMERIC(12,4) DEFAULT 0,
    itega_fee_pct   NUMERIC(4,4) DEFAULT 0.0150,
    itega_fee_amt   NUMERIC(12,4) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------
-- Home Base debits
-- What each Home Base owes for the content their
-- readers consumed during a settlement period.
-- ------------------------------------------------
CREATE TABLE home_base_debits (
    id              SERIAL PRIMARY KEY,
    settlement_id   INTEGER REFERENCES settlement_runs(id),
    home_base_id    VARCHAR(32) NOT NULL,
    total_events    INTEGER NOT NULL,
    total_wholesale NUMERIC(12,4) NOT NULL,
    amount_owed     NUMERIC(12,4) NOT NULL
);

-- ------------------------------------------------
-- Publisher credits
-- What each publisher earns for the content their
-- readers accessed during a settlement period.
-- ------------------------------------------------
CREATE TABLE publisher_credits (
    id              SERIAL PRIMARY KEY,
    settlement_id   INTEGER REFERENCES settlement_runs(id),
    pub_mbr_id      VARCHAR(32) NOT NULL,
    total_events    INTEGER NOT NULL,
    total_wholesale NUMERIC(12,4) NOT NULL,
    amount_earned   NUMERIC(12,4) NOT NULL
);

COMMIT;
