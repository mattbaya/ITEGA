-- ============================================================
-- Migration 003: ALS Settlement
-- Target database: als_settlement (VPS 2)
--
-- Settlement model: The ALS periodically aggregates access_events
-- from als_logs into settlement_runs. Each run produces per-home-base
-- debits (what the home base owes) and per-publisher credits (what
-- the publisher earns). The ITEGA fee is deducted from the gross
-- wholesale total before crediting publishers.
--
-- For the pilot, settlement is simulated (reports only, no real
-- money movement). Stripe Connect integration is deferred.
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
    amount_owed     NUMERIC(12,4) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hb_debits_settlement ON home_base_debits(settlement_id);

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
    amount_earned   NUMERIC(12,4) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pub_credits_settlement ON publisher_credits(settlement_id);

COMMIT;
