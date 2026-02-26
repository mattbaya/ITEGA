-- ============================================================
-- Migration 001: Newshare Profiles
-- Target database: newshare_profiles (VPS 1)
-- ============================================================

BEGIN;

-- ------------------------------------------------
-- PPID mapping table
-- Maps Keycloak subject IDs to pairwise pseudonymous
-- identifiers scoped per publisher.
-- ------------------------------------------------
CREATE TABLE ppid_mappings (
    id               SERIAL PRIMARY KEY,
    keycloak_user_id UUID NOT NULL,
    publisher_id     VARCHAR(32) NOT NULL,
    network_user_id  VARCHAR(128) NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    revoked_at       TIMESTAMPTZ,
    UNIQUE(keycloak_user_id, publisher_id)
);

CREATE INDEX idx_ppid_publisher    ON ppid_mappings(publisher_id);
CREATE INDEX idx_ppid_network_user ON ppid_mappings(network_user_id);

-- ------------------------------------------------
-- User preferences
-- Stores reader-controlled privacy and ad settings
-- that travel across the network.
-- ------------------------------------------------
CREATE TABLE user_preferences (
    keycloak_user_id UUID PRIMARY KEY,
    privacy_level    VARCHAR(16) DEFAULT 'limited',
    ad_preference    VARCHAR(16) DEFAULT 'full_ads',
    do_not_track     BOOLEAN DEFAULT FALSE,
    parental_control BOOLEAN DEFAULT FALSE,
    age_range        VARCHAR(8),
    markup_ratio     NUMERIC(4,2) DEFAULT 1.40,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------
-- Home Base configuration
-- Each Home Base is an OIDC-capable identity provider
-- that participates in the Newshare Network.
-- ------------------------------------------------
CREATE TABLE home_base_config (
    id               VARCHAR(16) PRIMARY KEY,
    name             VARCHAR(255) NOT NULL,
    domain           VARCHAR(255) NOT NULL,
    ppid_secret      VARCHAR(512) NOT NULL,
    default_markup   NUMERIC(4,2) DEFAULT 1.40,
    itega_cert_date  DATE,
    active           BOOLEAN DEFAULT TRUE
);

COMMIT;
