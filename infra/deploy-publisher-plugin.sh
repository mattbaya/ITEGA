#!/bin/bash
# deploy-publisher-plugin.sh — ship the plugin to a publisher site, as a unit.
#
#   ./deploy-publisher-plugin.sh <site> [<site> ...]
#   ./deploy-publisher-plugin.sh all
#
# e.g. ./deploy-publisher-plugin.sh barharbor
#      ./deploy-publisher-plugin.sh all
#
# This is the only supported route to a live publisher site. It exists because
# copying single files with scp took barharbor.info down: class-newshare-access.php
# had gained a third constructor argument, only that file was copied, and the
# bootstrap still passed two. Every page on the site returned a fatal error.
# See https://github.com/mattbaya/ITEGA/issues/11
#
# Three things prevent a repeat:
#
#   1. There is no way to deploy one file. The whole plugin directory ships or
#      nothing does, so a file can never meet an incompatible sibling.
#   2. Every PHP file is linted here, before anything leaves this machine.
#   3. The previous copy is kept, the new one is checked by fetching real pages,
#      and if the site stops answering it is put back automatically.
#
# The plugin's own configuration (member ID, API key) lives in newshare-config.php
# on the server and in the options table. Neither is touched.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/src/wordpress-plugin"

# site key -> ssh account | public URL.
# A case statement rather than an associative array: macOS still ships bash 3.2,
# where `declare -A` does not exist, and this script has to run from a laptop.
ALL_SITES="barharbor northberkshire wesmc"
site_config () {
    case "$1" in
        barharbor)      echo "barharbor@svaha.com|https://barharbor.info" ;;
        northberkshire) echo "northberkshire@svaha.com|https://northberkshire.org" ;;
        # West End Sentinel is an addon domain under the northberkshire account,
        # so it shares the ssh login but not the document root.
        wesmc)          echo "northberkshire@svaha.com|https://wesmc.org|wesmc.org" ;;
        *)              return 1 ;;
    esac
}

# Set per site below, since one account can serve more than one domain.
PLUGIN_DIR=''

red ()   { printf '\033[31m%s\033[0m\n' "$*"; }
green () { printf '\033[32m%s\033[0m\n' "$*"; }
bold ()  { printf '\033[1m%s\033[0m\n' "$*"; }

targets=()
if [[ $# -eq 0 ]]; then
    echo "usage: $0 <site> [<site> ...] | all" >&2
    echo "sites: $ALL_SITES" >&2
    exit 2
elif [[ "$1" == "all" ]]; then
    # shellcheck disable=SC2206  # deliberate word-splitting of a known-safe list
    targets=($ALL_SITES)
else
    targets=("$@")
fi

for t in "${targets[@]}"; do
    if ! site_config "$t" >/dev/null; then
        red "unknown site: $t (known: $ALL_SITES)"
        exit 2
    fi
done

# ---------------------------------------------------------------- lint, locally
# A parse error found here costs nothing. Found on the server, it is the whole
# site, because WordPress fatals before it renders anything at all.
bold "==> checking every PHP file parses"
if ! command -v php >/dev/null 2>&1; then
    red "php not found locally; refusing to deploy unlinted code"
    exit 1
fi
lint_failed=0
while IFS= read -r -d '' f; do
    if ! out=$(php -l "$f" 2>&1); then
        red "    $out"
        lint_failed=1
    fi
done < <(find "$SRC" -name '*.php' -not -path '*/vendor/*' -print0)
[[ $lint_failed -eq 0 ]] || { red "lint failed; nothing deployed"; exit 1; }
green "    ok"

# Dependencies must travel with it. Without vendor/ the plugin loads but every
# token validation fails, which looks like a login bug rather than a deploy one.
if [[ ! -d "$SRC/vendor" ]]; then
    bold "==> vendoring dependencies"
    ( cd "$SRC" && composer install --no-dev --optimize-autoloader --quiet )
fi

bold "==> packaging"
TARBALL="$(mktemp -d)/newshare-network.tgz"
trap 'rm -rf "$(dirname "$TARBALL")"' EXIT
# COPYFILE_DISABLE stops macOS writing ._AppleDouble members, which the remote
# tar then complains about at length.
COPYFILE_DISABLE=1 tar -czf "$TARBALL" -C "$SRC/.." \
    --exclude='.*' --exclude='composer.json' --exclude='composer.lock' \
    --exclude='newshare-config.php' \
    wordpress-plugin 2>/dev/null
echo "    $(du -h "$TARBALL" | cut -f1)"

# --------------------------------------------------------------------- deploy
overall=0
for site in "${targets[@]}"; do
    IFS='|' read -r account url docroot <<<"$(site_config "$site")"
    docroot="${docroot:-public_html}"
    echo
    bold "==> $site ($url)"

    scp -q -o BatchMode=yes -o ConnectTimeout=20 "$TARBALL" "$account:/tmp/newshare-network.tgz"

    # Unpack beside the live copy, preserve the site's own config file, swap,
    # and keep the old directory until the checks below have passed.
    ssh -o BatchMode=yes -o ConnectTimeout=20 "$account" "bash -s" <<REMOTE
set -euo pipefail
P="\$HOME/${docroot}/wp-content/plugins/newshare-network"
rm -rf /tmp/newshare-unpack
mkdir -p /tmp/newshare-unpack
# GNU tar warns about the xattr headers macOS bsdtar writes; the extract is fine.
tar -xzf /tmp/newshare-network.tgz -C /tmp/newshare-unpack --warning=no-unknown-keyword 2>/dev/null \
  || tar -xzf /tmp/newshare-network.tgz -C /tmp/newshare-unpack 2>/dev/null
NEW=/tmp/newshare-unpack/wordpress-plugin

# The provisioning file holds this publisher's member ID and API key. It is
# written once at install time and never shipped, so carry it across.
if [ -f "\$P/newshare-config.php" ]; then
    cp "\$P/newshare-config.php" "\$NEW/newshare-config.php"
fi

rm -rf "\$P.prev"
if [ -d "\$P" ]; then mv "\$P" "\$P.prev"; fi
mv "\$NEW" "\$P"
rm -f /tmp/newshare-network.tgz
rm -rf /tmp/newshare-unpack
echo "    swapped"
REMOTE

    # ---------------------------------------------------------------- verify
    # A plugin fatal takes down every page, so fetching real ones is the check
    # that matters. This is exactly how the outage was noticed.
    failed=""
    for path in "/" "/wp-json/newshare/v1/callback"; do
        code=$(curl -s -o /dev/null -w '%{http_code}' -L --max-time 25 "$url$path" || echo 000)
        # The callback with no parameters is expected to refuse; what matters is
        # that PHP answered at all rather than dying during plugin load.
        case "$path:$code" in
            "/:200") echo "    $path -> $code" ;;
            "/wp-json/newshare/v1/callback:"[24]*) echo "    $path -> $code" ;;
            *) red "    $path -> $code"; failed="$failed $path" ;;
        esac
    done

    # A 200 is not proof on its own: WordPress can render a page while the
    # plugin is silently broken, so look for the fatal in the log too.
    fatal=$(ssh -o BatchMode=yes -o ConnectTimeout=20 "$account" \
        "tail -c 4000 ~/${docroot}/wp-content/debug.log 2>/dev/null | grep -c 'Fatal error' || true")
    if [[ "${fatal:-0}" -gt 0 ]]; then
        # Only new fatals matter; check one arrived in the last two minutes.
        recent=$(ssh -o BatchMode=yes "$account" \
            "find ~/${docroot}/wp-content/debug.log -mmin -2 2>/dev/null | wc -l" || echo 0)
        [[ "${recent:-0}" -gt 0 ]] && failed="$failed debug.log"
    fi

    # Rehearsal: pretend the checks failed, so the rollback path runs for real
    # against a site that is perfectly healthy. This is how the rollback is
    # tested without ever putting broken code in front of a reader.
    if [[ -n "${NEWSHARE_DEPLOY_FORCE_FAIL:-}" ]]; then
        echo "    (rehearsal: forcing a failure to exercise the rollback)"
        failed="$failed rehearsal"
    fi

    if [[ -n "$failed" ]]; then
        red "    FAILED:$failed — rolling back"
        ssh -o BatchMode=yes "$account" "bash -s" <<REMOTE
set -euo pipefail
P="\$HOME/${docroot}/wp-content/plugins/newshare-network"
if [ -d "\$P.prev" ]; then
    rm -rf "\$P.failed"; mv "\$P" "\$P.failed"; mv "\$P.prev" "\$P"
    echo "    restored the previous plugin; the broken one is at \$P.failed"
else
    echo "    no previous copy to restore"
fi
REMOTE
        code=$(curl -s -o /dev/null -w '%{http_code}' -L --max-time 25 "$url/" || echo 000)
        if [[ "$code" == "200" ]]; then green "    site is back up ($code)"; else red "    STILL DOWN ($code) — go and look"; fi
        overall=1
    else
        green "    deployed and answering"
        ssh -o BatchMode=yes "$account" "rm -rf $HOME/${docroot}/wp-content/plugins/newshare-network.prev"
    fi
done

echo
if [[ $overall -eq 0 ]]; then
    green "All sites deployed."
else
    red "One or more sites failed and were rolled back."
fi
exit $overall
