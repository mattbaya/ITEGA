-- ============================================================
-- Migration 002: ALS Access Logs
-- Target database: als_logs (VPS 2, TimescaleDB)
-- ============================================================

BEGIN;

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ------------------------------------------------
-- Access events — the core audit log of the ALS.
-- Every content access across the Newshare Network
-- is recorded here for settlement and reporting.
-- ------------------------------------------------
CREATE TABLE access_events (
    timestamp        TIMESTAMPTZ NOT NULL,
    network_user_id  VARCHAR(128) NOT NULL,
    home_base_id     VARCHAR(32) NOT NULL,
    pub_mbr_id       VARCHAR(32) NOT NULL,
    resource_id      TEXT NOT NULL,
    page_class       NUMERIC(8,4) NOT NULL DEFAULT 0.00,
    service_class    INTEGER NOT NULL DEFAULT 0,
    markup_ratio     NUMERIC(4,2) NOT NULL DEFAULT 1.00,
    event_type       VARCHAR(32) NOT NULL DEFAULT 'content_access',
    session_id       VARCHAR(128) NOT NULL
);

-- Convert to a TimescaleDB hypertable partitioned by timestamp
SELECT create_hypertable('access_events', 'timestamp');

-- Indexes optimized for the three primary query patterns:
--   1. Settlement aggregation by home base over a time range
--   2. Settlement aggregation by publisher over a time range
--   3. Per-user access history
CREATE INDEX idx_events_home_base ON access_events(home_base_id, timestamp DESC);
CREATE INDEX idx_events_publisher ON access_events(pub_mbr_id, timestamp DESC);
CREATE INDEX idx_events_user      ON access_events(network_user_id, timestamp DESC);

COMMIT;
