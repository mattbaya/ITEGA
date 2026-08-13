#!/bin/bash
# beszel-agent-websocket.sh — switch a Beszel agent from listening to dialling out.
#
# Usage:  sudo ./beszel-agent-websocket.sh <hub-url> <token>
#
# By default the agent listens on a port and the hub connects *to* it, which
# means an inbound hole in the firewall on a production host. In WebSocket mode
# the agent dials out to the hub instead: no listener, no inbound rule, nothing
# on the public interface to get wrong. That is the better arrangement, and it
# also sidesteps a hub-to-agent connectivity problem seen on these hosts (see
# docs/monitoring.md) rather than requiring it to be solved.
#
# The token comes from the hub UI when a system is added.

set -euo pipefail

HUB_URL="${1:-}"
TOKEN="${2:-}"
if [[ -z "$HUB_URL" || -z "$TOKEN" ]]; then
    echo "usage: $0 <hub-url> <token>" >&2
    exit 2
fi

UNIT=/etc/systemd/system/beszel-agent.service

cat > "$UNIT" <<UNITFILE
[Unit]
Description=Beszel monitoring agent
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=beszel
Restart=on-failure
RestartSec=10
# Dial out to the hub rather than listening. No inbound port is opened, so
# nothing here is reachable from the internet.
Environment="HUB_URL=$HUB_URL"
Environment="TOKEN=$TOKEN"
ExecStart=/usr/local/bin/beszel-agent

[Install]
WantedBy=multi-user.target
UNITFILE

systemctl daemon-reload
systemctl restart beszel-agent
sleep 4

echo "  agent: $(systemctl is-active beszel-agent)"
if ss -tln 2>/dev/null | grep -q ":45876"; then
    echo "  WARNING: still listening on 45876 — expected no listener in this mode"
else
    echo "  no inbound listener — correct"
fi

# The inbound allow rule is now dead weight. Removing it keeps the firewall
# honest about what is actually reachable.
if grep -q "d=45876" /etc/csf/csf.allow 2>/dev/null; then
    sed -i '/beszel monitoring hub/d; /d=45876/d' /etc/csf/csf.allow
    csf -r >/dev/null 2>&1
    echo "  removed the now-unnecessary CSF inbound rule"
fi

journalctl -u beszel-agent --no-pager -n 5 2>/dev/null | tail -3 | sed 's/^/    /'
