# Monitoring

*Beszel — a hub with a web UI, and a lightweight agent on each monitored host.*

No credentials, addresses or keys appear here; this repository is public.

---

## What is running

| Host | Role | State |
|---|---|---|
| Monitoring host (cPanel shared account) | Hub, behind `monitor.itega.org` | Running, reporting |
| VPS 1 | Home base — Keycloak, Retail Agents | Agent up, reporting |
| VPS 2 | ITEGA — Authenticator, Logger, Directory | Agent up, reporting |
| Development host | Existing estate | Agent up, reporting |
| cPanel/DNS host | Existing estate — 548 DNS zones | Agent up, reporting |

All four report CPU, memory, disk, network and container stats.

## How the agents connect — and why it matters

The agents **dial out to the hub over 443**. They do not listen, and **no inbound
port is open on any monitored host** for monitoring.

That was not the original arrangement. Beszel's default has the hub connect *to*
an agent listening on port 45876, which needs an inbound hole on every monitored
machine. That was set up first and it did not work: with the firewall rule
confirmed present in `iptables` and the agent confirmed listening, connections
from the hub never completed, while the same host reached port 443 on the same
servers without trouble.

**The cause was the hub's own host, not the agents.** Installing agents on two
further servers — different providers, different firewalls — reproduced the
failure exactly. That ruled out the agents and their firewalls and pointed at the
one thing all attempts shared: the hub runs on a jailed cPanel account whose
outbound traffic is evidently restricted to standard ports.

Dial-out mode fixes it properly rather than working around it. Everything leaves
over 443, which is permitted everywhere, and the production hosts gained no
inbound exposure at all. The firewall rules added during the first attempt were
removed, so the firewall now reflects what is actually reachable.

Worth keeping in mind generally: when something fails identically across
independent networks, the common component is usually the culprit, and adding a
third data point is cheaper than deeper forensics on the first two.

## The hub

Served at `monitor.itega.org` over TLS, reverse-proxied from the cPanel account's
document root by `.htaccess`, because there is no root on that host to configure
a vhost. Three details there matter:

- **WebSocket upgrades are proxied**, not just plain HTTP. Beszel pushes live
  metrics over a WebSocket, and this is also how the agents connect. Without it
  the dashboard loads but never updates, which looks like the agents being down.
- **`.well-known/` bypasses the proxy**, verified by serving a real file from
  disk through it. Otherwise certificate renewal fails silently.
- **HTTP redirects to HTTPS.** Session cookies and agent tokens should never
  travel in clear.

There is no root, no Docker and no systemd on that host, so the hub runs as a
user process supervised by cron: `@reboot` plus a five-minute check that restarts
it if it has died. That is the only supervision available there and it is
adequate for this.

## Operational notes

**Adding another host.** Install the agent, create the system in the hub UI to
get a token, then set `HUB_URL`, `TOKEN` and `KEY` in the unit file.
`infra/beszel-agent-websocket.sh` does the last part. Note that `KEY` is required
even when dialling out — the agent refuses to start without it.

**Credentials.** The hub login was shared in a chat transcript during setup and
should be rotated.

## Backups

`restic` is installed on both Hetzner hosts, matching the existing estate, but is
**not yet scheduled**. Worth doing before the pilot carries anything worth losing.

One thing found while looking at the existing pattern: the equivalent job on the
development host has been failing its retention step since April. A stale lock
left `restic forget --prune` bailing out every night while the backup itself
succeeded, so snapshots have been accumulating for months. `restic unlock` clears
it. Worth checking any repository directly rather than trusting a green log —
the backup succeeding and the repository being healthy are different claims.
