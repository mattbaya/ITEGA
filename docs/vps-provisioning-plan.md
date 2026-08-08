# VPS Provisioning Plan — Aug 25 Demo

*What each piece of the network is, where it should run, and how to get the hosts
ready to receive code.*

## The constraint that drives the layout

ITEGA governs but does not operate. That is the whole argument of the project, and
the demo has to survive someone asking "so who runs that box?" So the split below is
not about resources — it is about which party operates what:

| Party | Operates | Runs on |
|---|---|---|
| A home base (e.g. Publisher C) | Keycloak realm, user accounts, **Retail Agent** | VPS 1 |
| ITEGA | Authenticator, Logger, Settlement, Network Directory | VPS 2 |
| Publishers | WordPress + the ITEGA plugin | Matt's existing sites |

**The Retail Agent must not live on the ITEGA box.** It holds the markup ratio and
decides whether to authorise a purchase — both of which are the home base's business,
and neither of which ITEGA is allowed to see. Co-locating it would contradict the
architecture on stage.

## Component inventory

### VPS 1 — Home Base (the ASP side)

| Component | Port | Purpose | Est. RAM |
|---|---|---|---|
| Keycloak 26.x | 8080 | OIDC provider; one realm per home base | 800–900 MB |
| PostgreSQL 16 | 5432 | Keycloak store + user profiles | 200–300 MB |
| `asp-agent` (×2) | 8003, 8004 | Retail Agent per home base — accept/counter/decline | 100–160 MB |
| Nginx + OS | 80/443 | TLS termination, Ubuntu 24.04 baseline | ~300 MB |
| **Idle total** | | | **~1.5–1.7 GB** |

**Size: 4 GB / 2 vCPU ($24/mo).** Keycloak's JVM is the whole cost here; everything
else is rounding. 2 GB would technically boot with `-Xmx512m` but leaves no headroom
for a live demo, which is exactly the wrong place to be tight.

### VPS 2 — ALS (the ITEGA side)

| Component | Port | Purpose | Est. RAM |
|---|---|---|---|
| TimescaleDB (PG16) | 5432 | `als_logs` + `als_settlement` | 200–300 MB |
| `als-auth` | 8000 | Authenticator: token issue/validate, home-base chooser | 50–80 MB |
| `als-logging` | 8001 | Logger: append-only event store, reports | 50–80 MB |
| `network-discovery` | 8002 | The ITEGA directory + WebFinger | 50–80 MB |
| `als-settlement` | — | Weekly cron batch, not a daemon | negligible |
| Nginx + dashboard | 80/443 | TLS, static React app | ~30 MB |
| OS | | Ubuntu 24.04 | ~300 MB |
| **Idle total** | | | **~700–900 MB** |

**Size: 2 GB / 1 vCPU ($12/mo) is genuinely enough**, even with the new discovery
service. 4 GB if you want room for TimescaleDB growth or a live-demo safety margin.

### Publishers — no new hosts

Three WordPress sites on Matt's existing hosting, running the `newshare-network`
plugin. The script casts Publishers A and B as content sites and Publisher C as the
home base; the transparent-SSO section needs a third content site to prove the login
travels. Each needs outbound HTTPS to VPS 1 and 2, and nothing else.

### Running total

| Option | VPS 1 | VPS 2 | Domain | Monthly |
|---|---|---|---|---|
| Comfortable | 4 GB $24 | 4 GB $24 | ~$1 | **~$49** |
| **Recommended** | 4 GB $24 | 2 GB $12 | ~$1 | **~$37** |

Well inside the $300–500/mo pilot budget, with room to add a second home-base host if
the independence story needs to be more literal (see below).

## One decision to make first: how many home bases?

The chooser is unconvincing with one option in it, and multi-home-base routing is now
built, so the demo wants at least two.

- **Two realms on one Keycloak (recommended).** Each realm has its own issuer, JWKS,
  and users — technically distinct in every way the ALS code cares about, and each
  gets its own Retail Agent. Costs nothing extra.
- **Two separate hosts.** More literally true to "different organisations," at +$12–24/mo
  and roughly double the setup. Worth it only if Bill expects to claim on the call that
  the home bases are genuinely independently operated.

The plan below assumes two realms on one host. Moving to two hosts later is a config
change, not a rewrite, because home bases are resolved from the registry rather than
hardcoded.

## DNS

| Name | Points at | Serves |
|---|---|---|
| `auth.<domain>` | VPS 1 | Keycloak (both realms) |
| `agent-c.<domain>` | VPS 1 | Publisher C's Retail Agent |
| `agent-demo.<domain>` | VPS 1 | Demo home base's Retail Agent |
| `als.<domain>` | VPS 2 | Authenticator + Logger |
| `network.<domain>` | VPS 2 | ITEGA directory |
| `dashboard.<domain>` | VPS 2 | User dashboard |

All A records, proxying off (needed for Let's Encrypt HTTP-01 and to keep the demo's
network path honest).

---

## Provisioning runbook

### Step 1 — Create the droplets

Ubuntu 24.04 LTS, in whichever region is nearest the Aug 25 audience. Add **both**
your SSH key and the deploy key from Step 3 at creation time; adding keys afterwards
means a console session.

```bash
doctl compute droplet create newshare-vps1 \
  --region nyc3 --image ubuntu-24-04-x64 --size s-2vcpu-4gb \
  --ssh-keys <your-key-id>,<deploy-key-id> --wait
```

```bash
doctl compute droplet create newshare-vps2 \
  --region nyc3 --image ubuntu-24-04-x64 --size s-1vcpu-2gb \
  --ssh-keys <your-key-id>,<deploy-key-id> --wait
```

*Creating droplets spends money, so this is yours to run — I won't provision
infrastructure on your account.*

### Step 2 — DNS

Point the six names above at the two droplet IPs and confirm propagation before
attempting certificates, or the ACME challenge fails and you burn rate limit:

```bash
for h in auth agent-c agent-demo als network dashboard; do dig +short $h.<domain>; done
```

### Step 3 — Access for me to push code

This is the part that decides whether I can work on these hosts directly.

Create a dedicated deploy key rather than reusing a personal one, so it can be revoked
without disturbing your own access:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/newshare_deploy -C "newshare-deploy" -N ""
```

Then either add `~/.ssh/newshare_deploy.pub` to a `deploy` user on both hosts, or add
a `Host newshare-vps1 / newshare-vps2` block to your `~/.ssh/config` pointing at it.
Once that exists I can run deploys and read logs over SSH the same way I do locally.

**What I'd need from you either way:** confirmation of the hostnames and the username
to connect as. I won't create accounts or install keys on remote hosts on my own.

### Step 4 — Base hardening (both hosts)

```bash
ssh root@<ip> 'adduser --disabled-password --gecos "" deploy && usermod -aG sudo deploy && rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy/'
```

Then disable password and root login in `/etc/ssh/sshd_config`
(`PermitRootLogin no`, `PasswordAuthentication no`), and:

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

Note the service ports (8000–8004, 5432) are deliberately **not** opened — every
container binds to `127.0.0.1` and is reached only through Nginx. Verify with
`ss -tlnp` that nothing is listening on `0.0.0.0` except Nginx and sshd.

### Step 5 — Docker

```bash
curl -fsSL https://get.docker.com | sh && usermod -aG docker deploy
```

### Step 6 — Code and secrets

```bash
git clone https://github.com/mattbaya/ITEGA.git /opt/newshare
```

Generate the secrets on the host — they should never exist on a laptop or in the repo:

```bash
openssl genrsa -out /opt/newshare/infra/vps2/secrets/jwt_private.pem 2048
openssl rsa -in /opt/newshare/infra/vps2/secrets/jwt_private.pem -pubout \
  -out /opt/newshare/infra/vps2/secrets/jwt_public.pem
```

`.env` per host (mode 0600, gitignored) needs: `POSTGRES_PASSWORD`,
`KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`, `SESSION_SECRET`, `ALS_API_KEY`,
`LOGGING_API_KEY`, `KC_HOSTNAME`, `ALS_BASE_URL`, `DISCOVERY_SERVICE_URL`, and
`PUBLISHERS_CONFIG`. Use `openssl rand -hex 32` for anything secret.

### Step 7 — TLS

```bash
apt install -y nginx certbot python3-certbot-nginx
certbot --nginx -d auth.<domain> -d agent-c.<domain> -d agent-demo.<domain>   # VPS 1
certbot --nginx -d als.<domain> -d network.<domain> -d dashboard.<domain>     # VPS 2
```

### Step 8 — Bring the stacks up

```bash
cd /opt/newshare/infra/vps1 && docker compose up -d
cd /opt/newshare/infra/vps2 && docker compose up -d
```

### Step 9 — Configure Keycloak

Per realm (`publisher-c`, `newshare`): create the realm, install the
`networkUserId` protocol mapper from `src/keycloak-spi/`, set subject type to
**pairwise** (this is the privacy guarantee — without it every publisher sees the same
user id), register an OIDC client per publisher with the ALS callback as redirect URI,
and create demo users.

### Step 10 — Verify before trusting it

```bash
curl -s https://network.<domain>/discovery/home-bases | jq '.[].name'
curl -s https://als.<domain>/auth/home-bases | jq
curl -s https://agent-c.<domain>/agent/policy | jq
curl -s -X POST https://agent-c.<domain>/agent/quote -H 'Content-Type: application/json' \
  -d '{"networkUserId":"t","homeBaseId":"HB001","pubMbrId":"P","resourceId":"/x","wholesalePrice":0.05}' | jq
```

Then the three-publisher SSO walkthrough in `demo-script-gap-analysis.md`.

---

## Work still needed before any of this will run

Found while writing this — the deployment config has not caught up with the code:

1. **`network-discovery` and `asp-agent` are not in any compose file.** Both have
   Dockerfiles and neither is wired up, so `docker compose up` brings up a stack
   missing two of the six services.
2. **`infra/vps2/network-discovery/` is stale.** It holds a static JSON file from when
   Plan 06 was going to be nginx-served. It is superseded by the real service and
   should go, or it will be served in preference to it and quietly answer with a
   registry that has one home base and no agent URLs.
3. **Nginx has no routes** for the discovery service or the agents, and currently
   serves `network.<domain>` from that stale directory.
4. **VPS 1 has no compose entry for the agents**, and no second realm.
5. **`PUBLISHERS_CONFIG`** needs real client IDs and secrets once the Keycloak clients
   exist.

Items 1–4 are self-contained and don't depend on anything from Bill. Say the word and
I'll do them, so that the runbook above is true when you follow it rather than after.
