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
Q=$(curl -s --max-time 20 -X POST https://agent-c.itega.org/agent/quote \
      -H 'Content-Type: application/json' \
      -d '{"networkUserId":"smoke","homeBaseId":"HB001","pubMbrId":"ITEGA-PA-0001",
           "resourceId":"/smoke","wholesalePrice":0.05,"terms":"final"}' 2>/dev/null)
if [[ "$Q" == *'"decision"'* ]]; then
  ok "Retail Agent quotes" "$(printf '%s' "$Q" | python3 -c 'import sys,json; print(json.load(sys.stdin)["decision"])' 2>/dev/null)"
else
  bad "Retail Agent quotes" "${Q:0:60}"
fi

echo
printf '  %d passed, %d failed\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
