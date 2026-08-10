# Server Specifications — Newshare Prototype

*What each host runs, what it costs, and why the split falls where it does.*

For the steps to build and configure these hosts, see
[`vps-provisioning-plan.md`](vps-provisioning-plan.md).

## Cheapest viable hosting

The sizing below is what the software needs. Where you rent it changes the bill by
roughly 4x for identical specs.

| Option | VPS 1 (4 GB) | VPS 2 (2 GB) | Monthly | Notes |
|---|---|---|---|---|
| **Hetzner Cloud** | CAX21 / CPX21 | CAX11 / CPX11 | **~$10–13** | US regions available (Ashburn VA, Hillsboro OR). Cheapest credible option. Verify current pricing. |
| DigitalOcean | s-2vcpu-4gb $24 | s-1vcpu-2gb $12 | ~$36 | Plan of record. Simplest tooling (`doctl`), most familiar. |
| Vultr / Linode | equivalent | equivalent | ~$30 | Between the two. |

**Recommendation: Hetzner in a US region.** Same specs, roughly a quarter of the
DigitalOcean bill, and the pilot budget line ($300–500/mo) is nowhere near either — so
the saving is not the point. The point is that a cheap monthly cost is easier to keep
running after Aug 25, when nobody is watching it.

### What about existing hardware?

`dev.svaha.com` was checked (Aug 2026): AlmaLinux 10, 2 vCPU, 7.5 GB RAM with ~3.4 GB
available, Docker 29.5 already installed. RAM is adequate for the ALS stack.

**But its disk is 91% full — 15 GB free of 157 GB**, and ports 80/443 are already
serving something. Container images plus database volumes for this stack run to several
gigabytes, and a disk-full event during a live demo is unrecoverable in the moment. It
could host the ALS side if the disk were cleared first and Nginx were integrated as a
vhost rather than standing alone, but it is not a good foundation for a date you cannot
move. Rent the two hosts.

---

## The principle behind the split

ITEGA governs but does not operate. That is the argument of the whole project, so the
division below is not primarily about resources — it is about which **party** operates
what:

| Party | Operates | Host |
|---|---|---|
| A home base (e.g. Publisher C) | Keycloak realm, user accounts, **Retail Agent** | VPS 1 |
| ITEGA | Authenticator, Logger, Settlement, Network Directory | VPS 2 |
| Publishers | WordPress + the `newshare-network` plugin | Existing sites |

**The Retail Agent must not live on the ITEGA host.** It holds the markup ratio and
decides whether to authorise a purchase — both the home base's business, and neither
of which ITEGA is permitted to see. Co-locating it would contradict the architecture
in front of an audience being asked to trust exactly that separation.

---

## VPS 1 — Home Base (the ASP side)

**DigitalOcean 4 GB / 2 vCPU — $24/mo — Ubuntu 24.04 LTS**

| Component | Port | Purpose | Est. RAM |
|---|---|---|---|
| Keycloak 26.x (Quarkus) | 8080 | OIDC provider; one realm per home base | 800–900 MB |
| PostgreSQL 16 | 5432 | Keycloak store + `newshare_profiles` | 200–300 MB |
| `asp-agent` (Publisher C) | 8003 | Retail Agent: accept / counter / decline | 50–80 MB |
| `asp-agent` (demo home base) | 8004 | Second Retail Agent | 50–80 MB |
| Nginx + OS | 80/443 | TLS termination, Ubuntu baseline | ~300 MB |
| **Idle total** | | | **~1.5–1.7 GB** |

**Why 4 GB:** Keycloak's JVM is effectively the entire cost here — tuned to
`-Xms256m -Xmx768m`, it idles around 500 MB and spikes past 1.2 GB under load.
Everything else on the host is rounding error. A 2 GB droplet would boot with
`-Xmx512m`, but leaves no headroom during a live demo, which is the worst possible
place to be tight.

**Storage:** 50 GB SSD (user profiles, PPID mappings, Keycloak state).

---

## VPS 2 — ALS (the ITEGA side)

**DigitalOcean 2 GB / 1 vCPU — $12/mo — Ubuntu 24.04 LTS**

| Component | Port | Purpose | Est. RAM |
|---|---|---|---|
| TimescaleDB (PG 16) | 5432 | `als_logs` + `als_settlement` | 200–300 MB |
| `als-auth` | 8000 | Authenticator: tokens, home-base chooser | 50–80 MB |
| `als-logging` | 8001 | Logger: append-only events, reports | 50–80 MB |
| `network-discovery` | 8002 | ITEGA directory + WebFinger | 50–80 MB |
| `als-settlement` | — | Weekly cron batch, not a daemon | negligible |
| Nginx + dashboard | 80/443 | TLS, static React build | ~30 MB |
| OS | | Ubuntu baseline | ~300 MB |
| **Idle total** | | | **~700–900 MB** |

**Why 2 GB is enough:** every ITEGA service is a lightweight async Python process;
TimescaleDB is the only real consumer. Even with the discovery service added, the host
idles under 1 GB. Choose 4 GB ($24) only if you want margin for TimescaleDB growth or
a live-demo safety buffer.

**Storage:** 25 GB SSD (10–20 GB of event logs at pilot volume; TimescaleDB compresses
well).

---

## Publishers — no new hosts

Three WordPress sites on existing hosting, each running the `newshare-network` plugin.

- The script casts **Publisher A** and **Publisher B** as content sites (CMS) and
  **Publisher C** as the home base (ASP only).
- The transparent-SSO section needs a **third content site** to prove a single login
  travels across the network.

Requirements per site: WordPress 6.x, PHP 8.1+, and outbound HTTPS to VPS 1 and VPS 2.
Nothing inbound beyond normal web traffic.

---

## Network exposure

Only 80 and 443 are open. Every service container binds to `127.0.0.1` and is reached
solely through Nginx; the service ports below are **not** externally reachable.

| Host | Open | Bound to loopback only |
|---|---|---|
| VPS 1 | 22, 80, 443 | 8080 (Keycloak), 8003–8004 (agents), 5432 |
| VPS 2 | 22, 80, 443 | 8000, 8001, 8002, 5432 |

Verify with `ss -tlnp` that nothing but `sshd` and `nginx` listens on `0.0.0.0`.

---

## DNS

| Name | Host | Serves |
|---|---|---|
| `auth.<domain>` | VPS 1 | Keycloak (all realms) |
| `agent-c.<domain>` | VPS 1 | Publisher C's Retail Agent |
| `agent-demo.<domain>` | VPS 1 | Demo home base's Retail Agent |
| `als.<domain>` | VPS 2 | Authenticator + Logger |
| `network.<domain>` | VPS 2 | ITEGA directory |
| `dashboard.<domain>` | VPS 2 | User dashboard |

All A records, proxying **off** — required for Let's Encrypt HTTP-01, and it keeps the
demo's network path honest rather than hidden behind a CDN.

---

## Cost

| Option | VPS 1 | VPS 2 | Domain | Monthly |
|---|---|---|---|---|
| **Recommended** | 4 GB — $24 | 2 GB — $12 | ~$1 | **~$37** |
| Comfortable | 4 GB — $24 | 4 GB — $24 | ~$1 | **~$49** |
| Two home bases | 2 × 4 GB — $48 | 2 GB — $12 | ~$1 | **~$61** |

All well inside the $300–500/mo pilot budget. The 18-month infrastructure line in the
funder brief is $5,400, so even the top option uses about a fifth of it.

---

## Open decision: how many home bases?

The home-base chooser is unconvincing with a single option in it, and multi-home-base
routing is now built, so the demo wants at least two.

| Approach | Cost | Trade-off |
|---|---|---|
| **Two realms, one Keycloak** *(recommended)* | $0 extra | Each realm has its own issuer, JWKS, and users — distinct in every way the ALS code cares about. Shared host. |
| Two Keycloak hosts | +$24/mo | Literally independent operation. Roughly doubles setup. |

Two realms is the pragmatic call: the "different organisations" claim is a governance
fact, not a hosting one. Choose two hosts only if Bill intends to assert genuine
independent operation on the call. Either way this is a configuration change rather
than a rewrite, because home bases are resolved from the ITEGA registry rather than
hardcoded anywhere.

---

## Caveat on these numbers

These are component-level estimates, not measurements — nothing has run under real
load yet. Keycloak in particular is worth watching once 50 users are on it. Revisit
after the first live run.
