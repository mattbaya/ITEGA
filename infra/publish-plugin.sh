#!/bin/bash
# Package the plugin, publish it, and tell installed copies about it.
#
# One command, because these four things must never drift apart: the zip, the
# checksum on the download page, the update manifest, and the version in the
# plugin header. Greylock Glass installed a build that was an hour stale and
# nobody could tell, which is the failure this script exists to prevent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src/wordpress-plugin"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VERSION=$(grep -m1 "^ \* Version:" "$SRC/newshare-network.php" | sed 's/.*Version: *//')
[ -n "$VERSION" ] || { echo "cannot read version"; exit 1; }
echo "==> version $VERSION"

echo "==> linting"
find "$SRC" -name '*.php' -not -path '*/vendor/*' -print0 \
  | xargs -0 -n1 php -l >/dev/null

echo "==> packaging"
rsync -a --exclude '.git*' --exclude '.DS_Store' --exclude 'newshare-config.php' \
      --exclude '*.log' "$SRC/" "$WORK/newshare-network/"
cat > "$WORK/newshare-network/newshare-config.php" <<'PHP'
<?php
/**
 * Provisioning defaults for this distribution.
 *
 * No credentials here and nothing to fill in: the plugin asks ITEGA for its
 * own Publishing Member ID, API key and demonstration key a few seconds after
 * activation, proving it controls the domain it is running on.
 *
 * Demo mode is on, and is not a checkbox. With it on, the plugin does nothing
 * at all for an ordinary reader: no gate, no pricing, nothing logged, no
 * status badge, and not even its stylesheet in your page source.
 *
 * @package Newshare_Network
 */

return array(
	'newshare_demo_mode'             => '1',
	'newshare_demo_key'              => '',
	'newshare_default_required_bits' => '0',
);
PHP
( cd "$WORK" && zip -q -r -X newshare-network.zip newshare-network -x '*.DS_Store' '__MACOSX/*' )

SUM=$(shasum -a 256 "$WORK/newshare-network.zip" | cut -d' ' -f1)
SIZE=$(du -h "$WORK/newshare-network.zip" | cut -f1)
echo "    $SIZE  sha256 $SUM"

echo "==> update manifest"
cat > "$WORK/update.json" <<JSON
{
  "name": "Newshare Network",
  "slug": "newshare-network",
  "version": "$VERSION",
  "author": "ITEGA",
  "homepage": "https://dashboard.itega.org/plugin/",
  "requires": "6.0",
  "requires_php": "8.1",
  "tested": "6.6",
  "last_updated": "$(date -u +%Y-%m-%d\ %H:%M:%S)",
  "download_url": "https://dashboard.itega.org/plugin/newshare-network.zip",
  "sha256": "$SUM",
  "sections": {
    "description": "Accept readers who hold an account at any other newspaper in the network, and be paid for what they read, without ever learning who they are. Full documentation at https://dashboard.itega.org/plugin/",
    "changelog": "<h4>$VERSION</h4><ul><li>Updates now arrive through WordPress, rather than by email asking you to reinstall.</li><li>In demonstration mode the plugin loads no stylesheet or script at all, so nothing of it appears in your page source.</li><li>Readers signed in to the network see who the site knows them as, and a way to sign out.</li><li>Demonstration mode is no longer a checkbox: it is pilot software, and the switch changed what every reader saw without warning.</li><li>US spelling throughout.</li></ul>"
  }
}
JSON
python3 -m json.tool "$WORK/update.json" >/dev/null || { echo "manifest is not valid JSON"; exit 1; }

echo "==> publishing"
sed -i '' "s|SHA-256 [a-f0-9]\{64\}|SHA-256 $SUM|" "$ROOT/scratchpad-plugin-index.html" 2>/dev/null || true
scp -q -i ~/.ssh/newshare_deploy "$WORK/newshare-network.zip" "$WORK/update.json" \
    deploy@als.itega.org:/tmp/
ssh -i ~/.ssh/newshare_deploy deploy@als.itega.org \
    "sudo mv /tmp/newshare-network.zip /tmp/update.json /var/www/dashboard/plugin/ \
     && sudo chown apache:apache /var/www/dashboard/plugin/* \
     && sudo chmod 644 /var/www/dashboard/plugin/*"

echo "==> verifying what is actually served"
SERVED=$(curl -s https://dashboard.itega.org/plugin/newshare-network.zip | shasum -a 256 | cut -d' ' -f1)
MANIFEST_V=$(curl -s https://dashboard.itega.org/plugin/update.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')
[ "$SERVED" = "$SUM" ] || { echo "    FAIL: served zip differs from the one built"; exit 1; }
[ "$MANIFEST_V" = "$VERSION" ] || { echo "    FAIL: manifest says $MANIFEST_V, plugin is $VERSION"; exit 1; }
echo "    zip matches, manifest says $MANIFEST_V"
echo
echo "Published $VERSION. Installed copies will offer the update within 12 hours."
