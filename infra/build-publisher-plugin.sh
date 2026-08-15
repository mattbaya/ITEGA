#!/bin/bash
# build-publisher-plugin.sh — package the plugin pre-configured for one publisher.
#
#   ./build-publisher-plugin.sh <pub-mbr-id> <api-key> [output-dir]
#
# e.g. ./build-publisher-plugin.sh ITEGA-PA-0001 "$ALS_API_KEY" ~/Desktop
#
# Produces newshare-network-<pub-mbr-id>.zip: the plugin with dependencies
# vendored and a provisioning file baked in, so activating it on a site leaves
# nothing to type. Everything network-level (the ALS and directory URLs) is
# already a default in the plugin itself; only the publisher's own member ID
# and the shared API key vary, and only those are written here.
#
# The generated zip contains a live API key. It is written outside the
# repository and must not be committed or posted anywhere public.

set -euo pipefail

PUB_MBR_ID="${1:-}"
API_KEY="${2:-}"
OUTDIR="${3:-$(pwd)}"

if [[ -z "$PUB_MBR_ID" || -z "$API_KEY" ]]; then
    echo "usage: $0 <pub-mbr-id> <api-key> [output-dir]" >&2
    exit 2
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/src/wordpress-plugin"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Dependencies must be vendored: a WordPress site has no composer, and without
# vendor/ the plugin loads but every token validation fails.
if [[ ! -d "$SRC/vendor" ]]; then
    echo "==> vendoring dependencies"
    ( cd "$SRC" && composer install --no-dev --optimize-autoloader --quiet )
fi

echo "==> staging"
mkdir -p "$STAGE/newshare-network"
rsync -a --exclude='.*' --exclude='composer.json' --exclude='composer.lock' \
      --exclude='newshare-config.php' "$SRC/" "$STAGE/newshare-network/"

echo "==> writing provisioning file for $PUB_MBR_ID"
cat > "$STAGE/newshare-network/newshare-config.php" <<PHPEOF
<?php
/**
 * Provisioning values for this publisher.
 *
 * Written by infra/build-publisher-plugin.sh at package time and read once, on
 * activation. Values already set on the site are never overwritten, and
 * anything defined in wp-config.php takes precedence over what is here.
 *
 * Contains a live API key: do not commit this file or the zip containing it.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

return array(
    'newshare_pub_mbr_id'  => '$PUB_MBR_ID',
    'newshare_als_api_key' => '$API_KEY',
);
PHPEOF

echo "==> checking it parses"
php -l "$STAGE/newshare-network/newshare-config.php" >/dev/null

ZIP="$OUTDIR/newshare-network-${PUB_MBR_ID}.zip"
rm -f "$ZIP"
( cd "$STAGE" && zip -qr "$ZIP" newshare-network )

echo "==> $ZIP"
echo "    $(unzip -l "$ZIP" | tail -1 | awk '{print $2}') files, $(du -h "$ZIP" | cut -f1)"
echo
echo "Install: Plugins > Add New > Upload Plugin, then activate."
echo "Everything is pre-filled; check Settings > Newshare Network to confirm."
