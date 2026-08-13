# Monitoring

*Beszel — a hub with a web UI, and a lightweight agent on each monitored host.*

No credentials, addresses or keys appear here; this repository is public.

---

## Where things run

| Piece | Host | State |
|---|---|---|
| Hub (web UI, stores history) | The cPanel shared host behind `monitor.itega.org` | **Running**, bound to loopback on a high port |
| Agent | VPS 1 (home base) | **Running** as a systemd service |
| Agent | VPS 2 (ALS) | **Running** as a systemd service |

## What is finished

**Agents** are installed at `/usr/local/bin/beszel-agent`, run as a dedicated
unprivileged `beszel` account under systemd, restart on failure, and start at
boot. They are in the agent's default mode: an SSH listener on port 45876 that
the hub connects *to*. The hub's public key is pinned in the unit file, so only
that one hub can talk to them.

CSF permits 45876 **only from the hub's address** — it is closed to everyone
else, which was verified from a third machine. The port is not on the internet.

**The hub** is installed under the monitoring account's home directory and
listens on loopback. There is no root, no Docker and no systemd on that host
— it is a jailed cPanel account — so the hub runs as a user process kept alive
by cron: `@reboot` plus a five-minute check that restarts it if it has died.
That is the only supervision available without systemd, and it is adequate.

## The hub is now public

`monitor.itega.org` serves the hub over TLS. It is reverse-proxied from the
cPanel account's document root by `.htaccess` rules, because there is no root on
that host to configure a vhost directly. Three details in those rules matter:

- **WebSocket upgrades are proxied**, not just plain HTTP. Beszel pushes live
  metrics over a WebSocket; without this the dashboard loads but never updates,
  which looks like the agents being down.
- **`.well-known/` bypasses the proxy**, verified by serving a real file from
  disk through it. Without that, certificate renewal fails silently.
- **HTTP redirects to HTTPS.** The hub sets session cookies and agents
  authenticate against this host; neither should travel in clear.

## What remains, and why it needs you

**The hub has no admin account.** Creating one means choosing a password, so it
is yours rather than mine:

1. Open `https://monitor.itega.org/` and create the first admin account.
2. Add each host as a system. The hub issues a **token** per system.
3. Apply the token on each host:

```bash
sudo /opt/newshare/infra/beszel-agent-websocket.sh https://monitor.itega.org <token>
```

That script switches the agent from listening to **dialling out** to the hub,
and removes the now-unnecessary inbound firewall rule. That is the arrangement
worth having: no listener and no inbound hole on a production host, and it
sidesteps the connectivity problem below rather than needing it solved.

If you would rather keep the current listening mode, the agents already trust
the hub's key and are running — only the connectivity issue below stands in the
way.

## One unresolved item

With CSF's allow rule confirmed present in `iptables` (`ACCEPT tcp -- <hub-ip>
… dpt:45876`), a connection from the hub to the agent port still does not
complete, while the same host reaches port 443 on the same servers without
trouble. The agent is confirmed listening on all interfaces and healthy.

This did not block anything else, so it was left rather than chased further. Two
things worth trying, in order:

- **Prefer the agent's WebSocket mode instead.** Recent Beszel versions let the
  *agent* dial out to the hub (`HUB_URL` plus a registration token from the UI)
  rather than listening. That removes the inbound port entirely — no CSF rule,
  no listener on a production host, nothing to get wrong. It needs the hub
  publicly reachable first, which is the cPanel step above, so it is the natural
  thing to do once that is done. **This is the better end state regardless of
  whether the current problem is diagnosed.**
- If staying with SSH mode, check whether the shared host applies egress
  filtering to non-standard ports; its outbound path is the untested half.

## Backups, while here

`restic` is installed on both hosts, matching the existing estate. It is not yet
scheduled — worth doing before the pilot carries anything worth losing, and worth
copying the existing pattern rather than inventing one.

Note that the equivalent job on the existing development host has been failing
its retention step since April: a stale lock left `restic forget --prune` bailing
out every night while the backup itself succeeded. Snapshots have been
accumulating since. `restic unlock` clears it. Worth checking any repository
before assuming a green backup log means a healthy repository.
