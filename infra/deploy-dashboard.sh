#!/usr/bin/env bash
#
# Build and deploy the reader dashboard to dashboard.itega.org.
#
# Until now this was a hand-copy. The publisher plugin got a real deploy path
# after a partial scp took barharbor.info down; the dashboard carried the same
# exposure with none of the protection, and it serves the /demo walkthrough that
# the Aug 25 roundtable is built around.
#
# Two things about the target make a naive sync dangerous:
#
#   * /var/www/dashboard is NOT only the React build. It also holds
#     preview-f45033ceaf/ -- 97 MB of narrated films and slides, served from an
#     unlisted URL that has been circulated -- and plugin/, the public download
#     and its update manifest. An rsync --delete over the docroot destroys both.
#   * Asset filenames are content-hashed, so old ones accumulate forever unless
#     something removes them. --delete is wanted *inside* assets/ and nowhere
#     else, which is exactly the distinction this script encodes.
#
# Usage:  infra/deploy-dashboard.sh
#         NEWSHARE_DEPLOY_FORCE_FAIL=1 infra/deploy-dashboard.sh   # rehearse rollback
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/src/dashboard"
KEY="${NEWSHARE_DEPLOY_KEY:-$HOME/.ssh/newshare_deploy}"
HOST="${NEWSHARE_DASHBOARD_HOST:-deploy@als.itega.org}"
ROOT="/var/www/dashboard"
URL="https://dashboard.itega.org"

red ()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn ()  { printf '\033[32m%s\033[0m\n' "$*"; }
bold () { printf '\033[1m%s\033[0m\n' "$*"; }

sshx () { ssh -o BatchMode=yes -o ConnectTimeout=20 -i "$KEY" "$HOST" "$@"; }

bold "==> building"
( cd "$SRC" && npm run build >/dev/null )
[ -f "$SRC/dist/index.html" ] || { red "no dist/index.html — build produced nothing"; exit 1; }
printf '    %s\n' "$(du -sh "$SRC/dist" | cut -f1) in dist"

# What the site must still be able to serve afterwards. Checked before and
# after, because the failure this guards against is silent: the app keeps
# working perfectly while 97 MB of films that were mailed to people stop
# existing.
bold "==> what must survive"
for keep in preview-f45033ceaf plugin robots.txt; do
    if sshx "test -e $ROOT/$keep"; then
        printf '    %s\n' "$keep"
    else
        red "    $keep is already missing before deploying — stop and look"
        exit 1
    fi
done

bold "==> uploading"
# Into a staging directory first, so a broken or interrupted transfer never
# becomes the live index.html.
sshx "rm -rf /tmp/dashboard-stage && mkdir -p /tmp/dashboard-stage"
rsync -a --delete -e "ssh -o BatchMode=yes -i $KEY" \
      "$SRC/dist/" "$HOST:/tmp/dashboard-stage/"

bold "==> swapping"
# The docroot is root-owned and its existing files belong to a uid that does not
# exist on the host (505:games), left by an earlier hand-copy from a Mac. The
# deploy user has passwordless sudo, so the swap runs through it and the result
# is chowned to apache, matching plugin/ next door.
sshx "sudo bash -s" <<REMOTE
set -euo pipefail
cd $ROOT
# Keep the previous build until the checks below pass.
rm -rf /tmp/dashboard-prev && mkdir -p /tmp/dashboard-prev
cp -a index.html /tmp/dashboard-prev/ 2>/dev/null || true
cp -a assets     /tmp/dashboard-prev/ 2>/dev/null || true

cp -a /tmp/dashboard-stage/index.html $ROOT/index.html
rm -rf $ROOT/assets
cp -a /tmp/dashboard-stage/assets $ROOT/assets
chown -R apache:apache $ROOT/index.html $ROOT/assets

# AppleDouble files from earlier hand-copies off a Mac. Harmless, but they are
# served, and ._index.html in a docroot looks like a leak to anyone who finds it.
find $ROOT -maxdepth 1 -name '._*' -delete
REMOTE

bold "==> checking what is served"
fail=0
check () {
    local path="$1" want="$2" label="$3"
    local got
    got=$(curl -s -o /dev/null -w '%{http_code}' "$URL$path" || echo 000)
    if [ "$got" = "$want" ] && [ "${NEWSHARE_DEPLOY_FORCE_FAIL:-}" != "1" ]; then
        printf '    %-34s %s\n' "$path" "$got"
    else
        red "    $path -> $got (wanted $want) — $label"
        fail=1
    fi
}
check "/"        200 "the dashboard itself"
check "/demo"    200 "the walkthrough, which must survive a reload"
check "/plugin/" 200 "the public plugin download"
check "/preview-f45033ceaf/" 200 "the films"

# The build is only right if the page it serves is the one just built.
asset=$(sed -n 's/.*assets\/\(index-[A-Za-z0-9]*\.js\).*/\1/p' "$SRC/dist/index.html" | head -1)
if [ -n "$asset" ] && curl -s "$URL/" | grep -q "$asset"; then
    printf '    %-34s %s\n' "served build" "$asset"
else
    red "    the page served is not the build just made ($asset)"
    fail=1
fi

if [ "$fail" = 1 ]; then
    red "==> rolling back"
    sshx "sudo cp -a /tmp/dashboard-prev/index.html $ROOT/index.html 2>/dev/null || true;
          sudo rm -rf $ROOT/assets;
          sudo cp -a /tmp/dashboard-prev/assets $ROOT/assets 2>/dev/null || true;
          sudo chown -R apache:apache $ROOT/index.html $ROOT/assets 2>/dev/null || true"
    red "rolled back to the previous build"
    exit 1
fi

for keep in preview-f45033ceaf plugin robots.txt; do
    sshx "test -e $ROOT/$keep" || { red "$keep did not survive the deploy"; exit 1; }
done

sshx "sudo rm -rf /tmp/dashboard-stage /tmp/dashboard-prev"
grn "Deployed, and the films and plugin download are still there."
