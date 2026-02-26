#!/bin/bash
# Creates the secondary database used for Newshare profile data.
# This script is executed automatically by the PostgreSQL entrypoint
# on first initialization only.

set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE newshare_profiles OWNER $POSTGRES_USER;
EOSQL
