# VPS Setup Record

*What was actually done to stand up the two servers, in order, including the
things that went wrong. Written so the build can be reproduced or audited.*

**No credentials, IP addresses, or secret values appear here.** Every secret is
generated on the host at deploy time and never enters this repository.

---

## What runs where

| Host | Role | Runs |
|---|---|---|
| VPS 1 | A home base (the ASP side) | Keycloak (two realms), PostgreSQL, two Retail Agents |
| VPS 2 | ITEGA (the ALS side) | Authenticator, Logger, Network Discovery, dashboard, settlement cron |

The split is by **which party operates what**, not by resource need. The Retail
Agent holds the markup ratio and decides whether to authorise a purchase — both
the home base's business, neither of which ITEGA may see. Putting it on the ITEGA
host would contradict the architecture the demo exists to argue for.

**Hosting:** Hetzner Cloud, Falkenstein. `cx33` (4 vCPU / 8 GB) and `cx23`
(2 vCPU / 4 GB), about $15.48/month combined. Hetzner's US regions cost roughly
3.4x their EU ones for identical hardware, which is worth knowing before
comparing quotes.

**OS:** AlmaLinux 10. **Firewall:** CSF. **Web server:** Apache.
**Database:** PostgreSQL (see the note at the end).

---

## 1. Create the servers

```bash
hcloud server create --name <name> --type cx33 --image alma-10 \
  --location fsn1 --ssh-key <key-name>
```

The `hcloud` CLI is authenticated on the operator's own machine
(`hcloud context create`), so the API token lives in their config and never
appears in a repository or a chat transcript. The token is project-scoped: it can
create and destroy servers in one project but cannot touch billing or the account.

**If the OS is wrong, rebuild rather than recreate.** `hcloud server rebuild
--image alma-10` keeps the same IP addresses, so DNS records already entered stay
valid. Deleting and recreating would change them.

## 2. DNS

Six A records, three per host, all proxying disabled — Let's Encrypt needs to
reach port 80 directly, and a proxy would also obscure the network path the demo
is meant to show honestly.

| Subdomain | Host | Serves |
|---|---|---|
| `auth` | VPS 1 | Keycloak, both realms |
| `agent-c` | VPS 1 | Retail Agent for home base HB001 |
| `agent-demo` | VPS 1 | Retail Agent for home base HB002 |
| `als` | VPS 2 | Authenticator and Logger |
| `network` | VPS 2 | ITEGA directory |
| `dashboard` | VPS 2 | Reader dashboard and the `/demo` walkthrough |

Confirm propagation **before** requesting certificates; a failed ACME challenge
consumes rate limit.

## 3. Bootstrap both hosts

`infra/bootstrap-almalinux.sh <vps1|vps2>` — idempotent, safe to re-run. It
creates an unprivileged `deploy` user, locks SSH to keys only and disables root
login, then installs Docker, Apache, CSF and restic.

Run it as root the first time. **It disables root SSH partway through**, so
subsequent runs go through the `deploy` user — which is the intended end state,
but will look like a lockout if you are not expecting it.

### Three things that went wrong here

**Docker would not start.** Alma's minimal cloud image ships without
`kernel-modules-extra`, so `xt_addrtype` is missing and dockerd dies with an
iptables error that reads like a firewall misconfiguration. Install
`kernel-modules-extra-$(uname -r)` — pinned to the *running* kernel, since the
unpinned package can pull modules for a newer kernel you have not booted — and
load the modules at boot via `/etc/modules-load.d/`.

**CSF's download host no longer exists.** ConfigServer Ltd shut down on 31 August
2025 and `download.configserver.com` does not resolve. CSF v15 was released under
GPLv3 and is continued at `configserver.dev`, actively maintained. Two practical
notes: the download sits behind Cloudflare and returns a challenge page to a
default curl user-agent, and plain servers want `install.generic.sh` rather than
`install.sh`.

**A shell bug that masked a working download.** The tarball integrity check was
written as `tar -tzf file | grep -q pattern`. Under `set -o pipefail` this fails
whenever grep *matches*: grep exits at the first hit, tar takes SIGPIPE, and the
pipeline reports failure precisely when the check has succeeded. List to a file
and grep the file instead.

## 4. Apache vhosts

Apache terminates TLS and reverse-proxies to containers bound on `127.0.0.1`. No
service port is ever exposed; CSF permits only 22, 80 and 443 inbound.

Configs are in `infra/vps1/apache/` and `infra/vps2/apache/`. Two details matter:

- **`ProxyPreserveHost On` for Keycloak.** Keycloak builds issuer URLs and
  redirect targets from the Host header. Without this every token is issued for
  `localhost` and the OIDC flow fails in ways that look like a client
  misconfiguration rather than a proxy one.
- **The dashboard falls back to `index.html`.** The React app owns its routing,
  so a reload on `/demo` would otherwise 404 mid-presentation.

Deploy them, then `httpd -t` before reloading.

## 5. Certificates

```bash
certbot-3 --apache --non-interactive --agree-tos --email <address> \
  --redirect --keep-until-expiring -d <domain> -d <domain> -d <domain>
```

The binary is **`certbot-3`** on Alma, not `certbot`. Certbot needs a port-80
vhost per domain to validate against, so step 4 must come first.

**AlmaLinux's certbot package ships no renewal timer or cron job.** Certificates
obtained this way simply expire after ninety days with nothing to warn anyone.
`infra/certbot-renew.service` and `infra/certbot-renew.timer` fill the gap; the
service reloads Apache afterwards, because Apache keeps the old certificate
loaded until told otherwise. Verify with `certbot-3 renew --dry-run`.

## 6. CSF and Docker — the fiddly part

CSF and Docker both want to own iptables. Getting this wrong presents as
containers that are demonstrably running and listening while every connection to
a published port hangs or resets — which looks like a broken application.

Three settings are required, and the order of operations matters:

```
DOCKER            = "1"
DOCKER_NETWORK4   = "172.16.0.0/12"     # covers compose's per-project subnets
ETH_DEVICE_SKIP   = "br-<id>,docker0"   # the compose bridge, not just docker0
```

`DOCKER = "1"` alone is not enough. CSF knows about `docker0`, but Docker Compose
creates a `br-<id>` bridge per project network, and CSF filters that bridge
unless told to skip it.

**Restart Docker after any CSF reload.** `csf -r` flushes iptables and takes
Docker's chains with it. A drop-in at
`/etc/systemd/system/docker.service.d/after-csf.conf` orders Docker after CSF at
boot, and `/usr/local/csf/bin/csfpost.sh` restarts Docker after each CSF reload.

To confirm CSF is genuinely the cause of a connectivity problem rather than
guessing: `csf -x` disables it entirely. If traffic flows immediately, it is CSF.
Re-enable with `csf -e` — do not leave it off.

**Run `csftest.pl` before setting `TESTING = "0"`.** It verifies the kernel
modules CSF depends on. Enabling a firewall that cannot actually apply its rules
gives a false sense of security, and enabling one that *can* over an SSH session
you depend on risks a lockout. Hetzner's web console is the way back in.

## 7. Deploy the stacks

Clone the repository to `/opt/newshare` on each host, write a `.env` (mode 0600,
gitignored), then `docker compose up -d --build` in the relevant `infra/vps*`
directory.

**Generate every secret on the host or on the operator's machine — never commit
them.** The repository ships `REPLACE-ME` placeholders for client secrets,
pairwise salts, demo passwords and AI agent keys, and they are substituted at
deploy time. The pairwise salts matter most: leaving the published values in place
would make the privacy guarantee meaningless, since the identifiers would be
predictable.

The ALS signing key is generated on VPS 2 with `openssl genrsa` and never leaves
it.

### Things that went wrong here too

**Keycloak refused to start because of JSON comments.** The realm files carried
`_comment` keys for documentation. Keycloak's importer rejects unrecognised
top-level fields and refuses to start the server at all — not a warning, a fatal
error. The explanations moved to `infra/vps1/realms/README.md`.

**`ls -d infra/vps*` matches `vps1` on both hosts.** Running that inside a loop
over both servers started the home-base stack on the ITEGA host as well. Worth
catching: it would have put the Retail Agents — and the markup ratio — on the
host that is explicitly not allowed to see them. Name the directory explicitly.

## 8. Verify

Check the public URLs rather than loopback; loopback can succeed while the proxy
or firewall path is broken.

```bash
curl -s https://<network-host>/discovery/home-bases
curl -s https://<als-host>/auth/home-bases
curl -s https://<agent-host>/agent/policy
```

Then exercise a real negotiation against the live agent, and confirm that two
home bases with different markups return different retail prices for the same
wholesale price. That single check proves the registry, both agents, the proxy
layer and the pricing model at once.

---

## Why PostgreSQL rather than MariaDB

Worth recording, since the rest of this estate runs MariaDB. Keycloak supports
MariaDB fine, but the ALS event store and settlement code do not port cheaply:
five files use PostgreSQL drivers, eighteen SQL statements would need converting,
and TimescaleDB has no MariaDB equivalent. Postgres also has the stronger query
planner for the aggregation settlement performs.

At pilot volume none of that is measurable. The deciding argument was not
database merit but risk: settlement is where a serious bug already lived once,
and rewriting its data layer shortly before a public demonstration would mean
re-verifying the money arithmetic under time pressure. Revisit after the demo if
consistency across the estate is wanted.
