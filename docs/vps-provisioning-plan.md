# VPS Provisioning Plan — Aug 25 Demo

*What each piece of the network is, where it should run, and how to get the hosts
ready to receive code.*

## Component sizing and layout

Moved to [`server-specs.md`](server-specs.md) — what each host runs, how it is sized,
which ports are exposed, and why the Retail Agent belongs on the home-base host rather
than the ITEGA one. Read that first; this document is the build steps.

**Short version:** VPS 1 (home base) Hetzner `cx33`, 8 GB / $8.99; VPS 2 (ALS)
`cx23`, 4 GB / $6.49; publishers on existing WordPress hosting. ~$16.48/mo including
the domain. (Earlier drafts of this line quoted $37/mo against DigitalOcean, which was
compared and not chosen.)

## What Matt needs to gather before starting

Four things, none of which I can obtain:

1. **A hosting account** with the two droplets created (see `server-specs.md` for the
   cheapest options). Spending money on your account is yours to do.
2. **A domain, and DNS control over it.** ITEGA already holds `itega.org`,
   `newshare.com`, `newssso.org` and others — using real subdomains
   (`auth.itega.org`, `als.itega.org`) makes the demo markedly more convincing than
   `newshare.example`, but needs Bill or whoever holds the DNS. Falling back to a
   domain you control is fine; decide early, because certificates depend on it.
3. **Three WordPress sites** you can install a plugin on, for Publishers A, B and the
   third site the transparent-SSO section needs.
4. **SSH access for me**, if you want a session to deploy and read logs directly
   (Step 3 below). Optional — you can run every command here yourself.

Do not send me registrar logins, hosting-account credentials, or passwords. A deploy
key and a hostname is the whole of what is useful.

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

## Deployment status

The stale blockers listed here previously — services missing from compose, the leftover
static discovery directory, absent Nginx routes, no second realm — are all resolved.
`docker compose up -d` on each host now brings up the full stack.

What genuinely remains, and cannot be done before the hosts exist:

1. **Replace every placeholder.** Realm client secrets, pairwise salts, demo passwords,
   the AI agent API keys in `src/als-auth/data/ai-agents.json`, and `PUBLISHERS_CONFIG`.
   All are marked `REPLACE-ME` and all are currently readable in a public repository.
2. **Register the publisher OIDC clients** and put their real IDs and secrets into
   `PUBLISHERS_CONFIG` on VPS 2.
3. **Point the registry at real hostnames.** `src/network-discovery/data/registry.json`
   still carries `.example` addresses.
4. **Walk every path end to end.** Nothing here has run against a live Keycloak,
   WordPress or Postgres. Assume the first full walkthrough finds something.
