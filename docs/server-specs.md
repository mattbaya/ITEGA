# Server Specifications — Newshare Prototype

*What each host runs, what it costs, and why the split falls where it does.*

For the steps to build and configure these hosts, see
[`vps-provisioning-plan.md`](vps-provisioning-plan.md).

## Cheapest viable hosting

The sizing below is what the software needs. Where you rent it changes the bill by
roughly 4x for identical specs.

**Chosen: Hetzner, Falkenstein (fsn1) — `cx33` + `cx23`, $15.48/mo.** Prices below were
read from the live API on Aug 10 2026, not from memory.

| Option | VPS 1 | VPS 2 | Monthly |
|---|---|---|---|
| **Hetzner EU** (fsn1/nbg1/hel1) | cx33 — 4 vCPU / 8 GB | cx23 — 2 vCPU / 4 GB | **$15.48** |
| Hetzner US (ash/hil) | cpx21 — 3 vCPU / 4 GB | cpx11 — 2 vCPU / 2 GB | $57.98 |
| InterServer | 2 slices | 1 slice | ~$18 |
| DigitalOcean | s-2vcpu-4gb | s-1vcpu-2gb | ~$36 |

**Hetzner's cheap reputation is EU-only.** Identical hardware in Ashburn costs 3.4x
Falkenstein — `cpx11` is $5.99 in fsn1 and $20.49 in ash. Quoting Hetzner's headline
price alongside a US region is an easy and expensive mistake to make.

Two other traps worth recording:

- **`cpx21` is discontinued** and cannot be ordered, though existing servers keep running.
- **The `cx` line beats the `cpx` line** on both price and size: `cx33` is 8 GB for
  $8.99 where `cpx21` was 4 GB for $10.99. Always read `hcloud server-type list` against
  the live API rather than trusting a remembered table.

*All vendors change their sheets; re-check before committing.*

**Hetzner vs InterServer.** On price and hardware Hetzner wins outright; it is the
cheapest credible RAM on the market and the machines are fast. Two things weigh the
other way for this particular job:

- **New Hetzner accounts are sometimes held for identity verification**, occasionally
  asking for photo ID, and that can take a day or more. With a fixed public date, that
  is a small but real risk. If you already have an account in good standing, it
  evaporates.
- **InterServer provisions immediately and is US-based**, including support, and its
  price-lock guarantee means the pilot's running cost will not drift after the demo.

The gap is roughly $6/mo — noise against a $300–500/mo budget line. **If you already
have a Hetzner account, use it. If you would be signing up today, InterServer removes a
scheduling risk for the price of a coffee.** Either is a sound choice; do not spend an
evening deciding.

### What about existing hardware?

Two of Matt's hosts were checked in August 2026.

**`dev.svaha.com`** — AlmaLinux 10, 2 vCPU, 7.5 GB RAM (~3.4 GB free), Docker present.
Ruled out on disk: **91% full, 15 GB free of 157 GB.** Images plus database volumes run
to several gigabytes, and a disk-full event mid-demo is unrecoverable in the moment.

**`bolt.svaha.com`** — AlmaLinux 9, 2 vCPU, 3.6 GB RAM (~2.5 GB free), 32 GB disk free,
Docker present, load average 0.02. On resources alone it could carry the ALS stack
comfortably. It is ruled out for a different reason: it is **a production server
answering DNS for 548 zones**, plus MariaDB, a Gogs git host and cPanel, behind csf/lfd.

That last point is the one that matters. Keycloak wants 4 GB to itself and would leave
this host with no margin; more importantly, an experiment that destabilises bolt takes
down DNS for 548 domains along with the demo. Coupling a public demonstration to a
production nameserver is a bad trade for the $10/mo it saves.

**Use bolt for DNS instead.** It already runs PowerDNS, which means the six A records
the demo needs can be created immediately, without waiting on ITEGA's registrar — a
genuine unblock, and a much better use of a box that is already doing that job well.

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

**What was actually bought**, and is running now:

| | Host | Spec | Monthly |
|---|---|---|---|
| VPS 1 — home base | Hetzner `cx33` | 8 GB / 4 vCPU | **$8.99** |
| VPS 2 — ALS | Hetzner `cx23` | 4 GB / 2 vCPU | **$6.49** |
| Domain | | | ~$1 |
| | | | **~$16.48** |

The options below were priced against DigitalOcean before Hetzner was chosen, and are
kept only to show the comparison that led to the decision. They are not what is running.

| Option | VPS 1 | VPS 2 | Domain | Monthly |
|---|---|---|---|---|
| DigitalOcean, recommended | 4 GB — $24 | 2 GB — $12 | ~$1 | ~$37 |
| DigitalOcean, comfortable | 4 GB — $24 | 4 GB — $24 | ~$1 | ~$49 |
| DigitalOcean, two home bases | 2 × 4 GB — $48 | 2 GB — $12 | ~$1 | ~$61 |

All well inside the $300–500/mo pilot budget. The 18-month infrastructure line in the
funder brief is $5,400; what is actually running uses about a twentieth of it.

---

## Open decision: how many home bases?

The home-base chooser is unconvincing with a single option in it, and multi-home-base
routing is now built, so the demo wants at least two.

| Approach | Cost | Trade-off |
|---|---|---|
| **Two realms, one Keycloak** *(recommended)* | $0 extra | Each realm has its own issuer, JWKS, and users — distinct in every way the ALS code cares about. Shared host. |
| Two Keycloak hosts | +$8.99/mo | Literally independent operation. Roughly doubles setup. |

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
