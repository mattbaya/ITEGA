#!/usr/bin/env bash
#
# Update the three demonstration sites the way a publisher does: through
# WordPress's own plugin updater, against the public manifest.
#
# Why not deploy-publisher-plugin.sh, which is faster and already works: because
# it is a path no real publisher has. Shipping to our own sites by rsync means
# the update mechanism every actual publisher depends on is exercised by nobody
# until it fails at their end. Greylock Glass would have been the first to find
# out, which is the wrong way round.
#
# So this drives the same three steps a publisher's WordPress does:
#
#   1. Ask dashboard.itega.org/plugin/update.json what the current version is.
#   2. Download the zip it names.
#   3. Unpack it over the installed copy.
#
# Both caches are cleared first -- ours (12 hours) and WordPress's own -- since
# otherwise the update appears not to exist and the run proves nothing.
#
# Credentials survive this. They live in WordPress options, not in the plugin
# directory, which the updater deletes and replaces. newshare-config.php only
# supplies defaults at activation and its loss is not felt.
#
# Run infra/publish-plugin.sh first. This installs what is published, not what
# is in the working tree, which is the entire point.
#
# Usage:  infra/update-demo-sites.sh [barharbor|northberkshire|wesmc|all]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="https://dashboard.itega.org/plugin/update.json"
ALL_SITES="barharbor northberkshire wesmc"

red ()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn ()  { printf '\033[32m%s\033[0m\n' "$*"; }
bold () { printf '\033[1m%s\033[0m\n' "$*"; }

site_config () {
    case "$1" in
        barharbor)      echo "barharbor|public_html|https://barharbor.info" ;;
        northberkshire) echo "northberkshire|public_html|https://northberkshire.org" ;;
        # West End Sentinel is an addon domain under the northberkshire account.
        wesmc)          echo "northberkshire|wesmc.org|https://wesmc.org" ;;
        *)              return 1 ;;
    esac
}

targets=("${@:-all}")
[ "${targets[0]}" = "all" ] && targets=($ALL_SITES)

published=$(curl -fsS "$MANIFEST" | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')
bold "==> published: $published"

fail=0
for t in "${targets[@]}"; do
    cfg=$(site_config "$t") || { red "unknown site: $t"; exit 1; }
    account=${cfg%%|*}; rest=${cfg#*|}; docroot=${rest%%|*}; url=${rest##*|}

    bold "==> $t ($url)"
    wp () { ssh -o BatchMode=yes -o ConnectTimeout=20 "$account@svaha.com" \
            "export PATH=\$HOME/bin:\$PATH; cd \$HOME/$docroot; wp $*" 2>/dev/null; }

    before=$(wp plugin get newshare-network --field=version)
    printf '    installed: %s\n' "$before"

    # Our manifest cache and WordPress's update cache. Without clearing both,
    # the site reports itself current and this script proves nothing at all --
    # the failure mode is a green run over an update that never happened.
    wp transient delete newshare_update_manifest >/dev/null || true
    wp transient delete update_plugins --network >/dev/null 2>&1 || true
    wp transient delete update_plugins >/dev/null 2>&1 || true

    if [ "$before" = "$published" ]; then
        printf '    already on the published version — nothing to prove here\n'
    else
        # WordPress fetches the manifest, downloads the zip it names, and
        # unpacks it. Exactly what a publisher's dashboard does.
        wp plugin update newshare-network >/dev/null || true
    fi

    after=$(wp plugin get newshare-network --field=version)
    if [ "$after" = "$published" ]; then
        printf '    now: %s\n' "$after"
    else
        red "    now: $after — did not reach $published"
        fail=1
    fi

    # The updater deletes the plugin directory. Credentials must have survived
    # in options, or the site is silently unable to price or log anything.
    mbr=$(wp option get newshare_pub_mbr_id)
    key=$(wp option get newshare_als_api_key)
    if [ -n "$mbr" ] && [ -n "$key" ]; then
        printf '    credentials intact: %s\n' "$mbr"
    else
        red "    credentials lost — the site is de-provisioned"
        fail=1
    fi

    # And the reader-facing result, not just the version string.
    code=$(curl -s -o /dev/null -w '%{http_code}' "$url/")
    if [ "$code" = "200" ]; then
        printf '    %s -> 200\n' "$url"
    else
        red "    $url -> $code"
        fail=1
    fi
done

if [ "$fail" = 1 ]; then
    red "Something did not update cleanly. deploy-publisher-plugin.sh is the way back."
    exit 1
fi
grn "All sites updated through WordPress's own updater."
echo "Run infra/journey-test.py and infra/reader-eyes-test.py to confirm the reader's path."
