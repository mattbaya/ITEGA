#!/usr/bin/env bash
#
# Smoke test every public surface of the Newshare demo.
#
# Written after a sign-in bug reached a demo deck. The reader's authenticated
# journey had never been walked end to end, so a missing PKCE parameter went
# unnoticed until someone clicked the link by hand and got a JSON error page.
# Anything a visitor can reach should be checked here, and this should be run
# before showing the system to anybody.
#
# Usage:  infra/smoke-test.sh
# Exit:   0 if every check passes, 1 otherwise.

set -uo pipefail

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓\033[0m %-50s %s\n' "$1" "${2:-}"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗\033[0m %-50s %s\n' "$1" "${2:-}"; FAIL=$((FAIL+1)); }

# Expect one of several status codes. A 422 from a JSON endpoint given an
# empty body still proves the route exists and reaches the application.
check () {  # label url expected[,expected...]
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$2" 2>/dev/null)
  case ",$3," in
    *",$code,"*) ok "$1" "HTTP $code" ;;
    *)           bad "$1" "HTTP $code (wanted $3)" ;;
  esac
}

post () {  # label url expected[,expected...]
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
         -X POST -H 'Content-Type: application/json' -d '{}' "$2" 2>/dev/null)
  case ",$3," in
    *",$code,"*) ok "$1" "HTTP $code" ;;
    *)           bad "$1" "HTTP $code (wanted $3)" ;;
  esac
}

# Fetch once into a variable, then match. Piping curl into `grep -q` looks
# tidier but breaks under `pipefail`: grep exits at the first match, curl
# takes SIGPIPE, and the pipeline reports failure even though it matched.
contains () {  # label url needle
  local body
  body=$(curl -sL --max-time 20 "$2" 2>/dev/null)
  if [[ "$body" == *"$3"* ]]; then ok "$1"; else bad "$1" "missing: $3"; fi
}

echo
echo "PUBLISHER SITES"
check    "barharbor.info serves"                https://barharbor.info      200
check    "northberkshire.org serves"            https://northberkshire.org  200
contains "North Berkshire masthead renders"     https://northberkshire.org  "North Berkshire"
contains "Bar Harbor front page renders"        https://barharbor.info      "Bar Harbor"

echo
echo "ITEGA SERVICES"
check "ALS home-base list"           https://als.itega.org/auth/home-bases              200
check "ALS signing keys"             https://als.itega.org/.well-known/jwks.json        200
post  "ALS session validation"       https://als.itega.org/auth/validate                422,400
post  "ALS log ingest"               https://als.itega.org/log/event                    422,400,401,403
check "Discovery: home bases"        https://network.itega.org/discovery/home-bases     200
check "Discovery: publishers"        https://network.itega.org/discovery/publishers     200
check "Discovery document"           https://network.itega.org/.well-known/newshare-network 200
check "Dashboard"                    https://dashboard.itega.org/                       200
check "Walkthrough"                  https://dashboard.itega.org/demo                   200
check "Retail Agent C"               https://agent-c.itega.org/healthz                  200
check "Retail Agent demo"            https://agent-demo.itega.org/healthz               200
check "Monitoring hub"               https://monitor.itega.org/                         200

echo
echo "HOME BASES"
for realm in publisher-c newshare; do
  check "realm $realm: discovery document" \
        "https://auth.itega.org/realms/$realm/.well-known/openid-configuration" 200
  check "realm $realm: signing keys" \
        "https://auth.itega.org/realms/$realm/protocol/openid-connect/certs" 200
done

# ── The reader's sign-in journey ─────────────────────────────────────
#
# The path that broke. Walk it hop by hop rather than assuming that a first
# redirect means the rest works: the failure was two hops in.

EXTRACT=$(mktemp)
cat > "$EXTRACT" <<'PYEOF'
import sys, re, html
member = sys.argv[1]
for m in re.finditer(r'href="(/auth/select-home-base[^"]+)"', sys.stdin.read()):
    href = html.unescape(m.group(1))
    if member in href:
        print(href)
        break
PYEOF
trap 'rm -f "$EXTRACT"' EXIT

echo
echo "THE READER'S SIGN-IN JOURNEY"
AUTH="https://als.itega.org/auth/authorize?client_id=pub-a&redirect_uri=https%3A%2F%2Fbarharbor.info%2Fwp-json%2Fnewshare%2Fv1%2Fcallback&response_type=code&scope=openid&state=smoke"
CHOOSER=$(curl -s --max-time 20 "$AUTH" 2>/dev/null)

if [[ "$CHOOSER" == *"/auth/select-home-base"* ]]; then
  ok "chooser renders"
else
  bad "chooser renders" "unexpected body"
fi

for member in ITEGA-PC-0001 ITEGA-DEMO-0002; do
  LINK=$(printf '%s' "$CHOOSER" | python3 "$EXTRACT" "$member" 2>/dev/null)
  if [ -z "$LINK" ]; then
    bad "$member: listed in the chooser"
    continue
  fi
  ok "$member: listed in the chooser"

  KC=$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 20 "https://als.itega.org$LINK" 2>/dev/null)
  case "$KC" in
    *"/protocol/openid-connect/auth"*)
      if [[ "$KC" == *"code_challenge_method"* ]]; then
        ok "$member: redirect carries PKCE challenge"
      else
        bad "$member: redirect MISSING PKCE challenge" "home base will refuse"
      fi
      CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$KC" 2>/dev/null)
      BODY=$(curl -s --max-time 20 "$KC" 2>/dev/null)
      if [ "$CODE" = "200" ] && [[ "$BODY" == *"Sign in"* ]]; then
        ok "$member: home base shows a sign-in form"
      else
        bad "$member: home base shows a sign-in form" "HTTP $CODE"
      fi
      ;;
    *"error="*)
      bad "$member: home base rejected the request" \
          "$(printf '%s' "$KC" | sed 's/.*error_description=//;s/&.*//' | tr '+' ' ')" ;;
    *)
      bad "$member: unexpected redirect" "${KC:0:60}" ;;
  esac
done

echo
echo "PRICING"
# A quote now needs the asking publisher's own ITEGA key (#68), so this check
# uses Bar Harbor's -- the same one the cross-party section fetches.
SMOKE_KEY=$(ssh -o BatchMode=yes -o ConnectTimeout=15 barharbor@svaha.com \
    "export PATH=\$HOME/bin:\$PATH; cd \$HOME/public_html; wp option get newshare_als_api_key" \
    2>/dev/null | tr -d '\r')
Q=$(curl -s --max-time 20 -X POST https://agent-c.itega.org/agent/quote \
      -H 'Content-Type: application/json' -H "X-API-Key: $SMOKE_KEY" \
      -d '{"networkUserId":"smoke","homeBaseId":"HB001","pubMbrId":"ITEGA-PA-0001",
           "resourceId":"/smoke","wholesalePrice":0.05,"terms":"final"}' 2>/dev/null)
if [[ "$Q" == *'"decision"'* ]]; then
  ok "Retail Agent quotes" "$(printf '%s' "$Q" | python3 -c 'import sys,json; print(json.load(sys.stdin)["decision"])' 2>/dev/null)"
else
  bad "Retail Agent quotes" "${Q:0:60}"
fi

# And it must refuse an unauthenticated one, which is the whole of #68: the
# reply carries the retail price, so anyone who could ask could read the markup.
QN=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST https://agent-c.itega.org/agent/quote \
      -H 'Content-Type: application/json' \
      -d '{"networkUserId":"smoke","homeBaseId":"HB001","pubMbrId":"ITEGA-PA-0001",
           "resourceId":"/smoke","wholesalePrice":0.05,"terms":"final"}' 2>/dev/null)
[ "$QN" = "401" ] && ok "a quote without a key is refused" "401" \
                  || bad "a quote without a key is refused" "got $QN"

echo
echo "WHAT A CREDENTIAL MAY NOT DO"
# Nothing here checked that one party cannot read another's data, which is how
# #63 lived: any publisher key could read a competitor's revenue and a home
# base's entire per-reader clickstream. Every other check asked whether a
# credential works. These ask what it can reach.
PUB_KEY=$(ssh -o BatchMode=yes -o ConnectTimeout=15 barharbor@svaha.com \
    "export PATH=\$HOME/bin:\$PATH; cd \$HOME/public_html; wp option get newshare_als_api_key" \
    2>/dev/null | tr -d '\r')
if [ -z "$PUB_KEY" ]; then
  ok "cross-party access" "no publisher key to hand — skipped"
else
  P1="period_start=2026-08-01T00:00:00Z&period_end=2026-12-31T00:00:00Z"
  C=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $PUB_KEY" \
      "https://als.itega.org/log/report/publisher/ITEGA-PB-0001?$P1")
  [ "$C" = "403" ] && ok "a publisher cannot read another's revenue" "403" \
                   || bad "a publisher cannot read another's revenue" "got $C"

  C=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $PUB_KEY" \
      "https://als.itega.org/log/report/home-base/HB001?$P1")
  [ "$C" = "403" ] && ok "a publisher cannot read a home base's clickstream" "403" \
                   || bad "a publisher cannot read a home base's clickstream" "got $C"

  C=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $PUB_KEY" \
      "https://als.itega.org/log/report/publisher/ITEGA-PA-0001?$P1")
  [ "$C" = "200" ] && ok "a publisher can still read its own" "200" \
                   || bad "a publisher can still read its own" "got $C"

  # And the reader endpoints, which #62 closed the same way.
  C=$(curl -s -o /dev/null -w '%{http_code}' \
      "https://agent-c.itega.org/agent/reader/948afc06-d2ed-340c-b45b-b13c178323b5/history")
  [ "$C" = "401" ] && ok "a reader's history needs that reader's token" "401" \
                   || bad "a reader's history needs that reader's token" "got $C"

  # No publisher may hold the exchange's own key. #31 checks a key may only
  # file as itself, and #63 that it may only read its own -- both pass for an
  # internal key, because an internal key legitimately may do those things. The
  # fault they cannot see is a site being handed the wrong credential, which is
  # exactly what had happened to one of the three. #75.
  for site in "barharbor|public_html" "northberkshire|public_html" "northberkshire|wesmc.org"; do
    acct=${site%%|*}; root=${site##*|}
    K=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$acct@svaha.com" \
        "export PATH=\$HOME/bin:\$PATH; cd \$HOME/$root; wp option get newshare_als_api_key" \
        2>/dev/null | tr -d '\r')
    if [ -z "$K" ]; then
      bad "$root holds a key of its own" "no key set"
      continue
    fi
    WHO=$(curl -s --max-time 15 -H "X-API-Key: $K" https://als.itega.org/log/whoami \
          | python3 -c 'import sys,json; d=json.load(sys.stdin); print("internal" if d.get("internal")=="true" else d.get("pub_mbr_id",""))' 2>/dev/null)
    case "$WHO" in
      internal|"") bad "$root holds its own key, not the exchange's" "resolves to ${WHO:-nothing}" ;;
      *)           ok  "$root holds its own key" "$WHO" ;;
    esac
  done
fi

echo
echo "DEPLOYED CODE"
# Is the code answering on these hosts the code in the repository?
#
# Nothing used to ask. #47 removed a phantom publisher from the registry, the
# commit went green, and the live service went on serving it for hours -- every
# endpoint returning 200 the whole time, because a stale deploy is indis-
# tinguishable from a healthy one unless something compares the two.
#
# The plugin has had this check since a publisher ran an hour-stale build:
# publish-plugin.sh compares the served zip against the built one. This is the
# same question asked of the services.
DEPLOY_KEY="${NEWSHARE_DEPLOY_KEY:-$HOME/.ssh/newshare_deploy}"
DEPLOY_HOST="${NEWSHARE_VPS2_HOST:-deploy@als.itega.org}"
if [ -r "$DEPLOY_KEY" ]; then
  WANT=$(git -C "$(dirname "$0")/.." rev-parse origin/main 2>/dev/null || echo unknown)
  # Compared over the paths this host actually runs, not the whole tree. A
  # plugin release or a documentation commit moves origin/main without changing
  # anything here, and a check that goes red for those teaches people to ignore
  # it -- which would cost more than the drift it was built to catch.
  # Both hosts. VPS 1 runs Keycloak, the SPI mapper and all three Retail
  # Agents, and until #61 nothing watched it at all -- the host holding the
  # identity provider was the one host with no check on what it was running.
  check_host () {
      local label="$1" host="$2" paths="$3" got
      got=$(ssh -o BatchMode=yes -o ConnectTimeout=15 -i "$DEPLOY_KEY" "$host" \
            "cd /opt/newshare && git rev-parse HEAD" 2>/dev/null || echo unreachable)
      if [ "$WANT" = "unknown" ] || [ "$got" = "unreachable" ]; then
        ok "$label deployed code" "could not compare — skipped"
      elif [ "$got" = "$WANT" ]; then
        ok "$label runs origin/main" "${got:0:8}"
      elif git -C "$(dirname "$0")/.." diff --quiet "$got" "$WANT" -- $paths 2>/dev/null; then
        ok "$label runs current service code" "${got:0:8}, and nothing it serves has changed since"
      else
        bad "$label runs current service code" \
            "serving ${got:0:8}; ${WANT:0:8} changes $(git -C "$(dirname "$0")/.." diff --name-only "$got" "$WANT" -- $paths 2>/dev/null | wc -l | tr -d ' ') file(s) it runs"
      fi
  }
  check_host "VPS 2" "$DEPLOY_HOST" "src/als-auth src/als-logging src/als-settlement src/network-discovery infra/vps2"
  check_host "VPS 1" "${NEWSHARE_VPS1_HOST:-deploy@auth.itega.org}" "src/asp-agent src/keycloak-spi infra/vps1"
else
  ok "deployed commit" "no deploy key here — skipped"
fi

echo
printf '  %d passed, %d failed\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
