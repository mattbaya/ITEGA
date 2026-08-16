# CLAUDE.md — Project Instructions for Claude Code

## Project: ITEGA / Newshare Network

This repository contains the technical review, planning documents, and working prototype
implementation for the Newshare Network, governed by ITEGA.

## Architecture Context

The Newshare Network uses a **four-party federated model** — NOT a centralized platform:

1. **End User** — registers once at a home base
2. **Home Base (IdSP)** — the ONLY party that knows the user's real identity
3. **Publisher (Content Provider)** — accepts users from any home base via WordPress plugin
4. **ALS (Auth/Logging/Settlement)** — neutral infrastructure that validates tokens, logs events, settles payments

**ITEGA** governs but does NOT operate. It is analogous to Visa International or ICANN.

Key architectural constraints that must be preserved in ALL code and documentation:
- **No cookies.** Authentication state is passed via HTTP headers and signed JWT tokens only.
- **Pairwise Pseudonymous Identifiers (PPID).** Each user gets a DIFFERENT opaque ID at each publisher. Cross-site correlation is architecturally impossible without home base cooperation.
- **PII never leaves the home base.** The ALS only sees opaque `networkUserId` and `networkGroupId`.
- **Wholesale-retail pricing.** Publishers set wholesale `pageClass`; home bases set retail `markupRatio`.
- **No central identity database.** The network is distributed like DNS.

## Protocol Stack

When writing code or documentation, use these specific protocols:
- **OIDC 1.0** (Authorization Code Flow) for SSO
- **JWT** (RFC 7519) for tokens, signed with RS256
- **WebFinger** (RFC 7033) for home-site discovery
- **OIDC PPID** for pairwise pseudonymous identifiers
- **W3C Verifiable Credentials** (VC Data Model 2.0) for rich identity claims
- **JWE** (RFC 7516) for sensitive token claims
- **RSL** (Really Simple Licensing, rslstandard.org) for content rights tagging
- **TLS 1.3** mandatory for all network connections
- **NetworkGroupId** — custom bitmask claim in OIDC ID Token for subscription tiers

## Repository Structure

```
ITEGA/
├── CLAUDE.md                   ← You are here
├── README.md                   ← Verbose project overview with examples
├── docs/
│   ├── STATUS.md               ← START HERE. Living handoff: state, plan, decisions
│   ├── vps-setup-record.md     ← How the servers were built, and what went wrong
│   ├── monitoring.md           ← Beszel hub and agents
│   ├── publisher-sites.md      ← The two WordPress publisher sites
│   ├── demo-script-gap-analysis.md ← Aug 25 demo script vs. the code; open questions
│   ├── peer-review-synthesis.md ← Synthesis of Drummond Reed + Don Marti feedback
│   ├── response-to-bill.md     ← Summary for Bill Densmore
│   └── source-pdfs/            ← Original documents from Bill Densmore
├── reference/                  ← GITIGNORED. Source PDFs, correspondence, and Bill's
│                                  working demo scripts. Local only — this repo is public.
├── plans/
│   ├── 00-system-architecture-overview.md
│   ├── 01-home-base-idsp-server.md
│   ├── 02-als-authentication-service.md
│   ├── 03-als-logging-service.md
│   ├── 04-als-settlement-service.md
│   ├── 05-publisher-wordpress-plugin.md
│   ├── 06-network-discovery-service.md
│   └── 07-user-dashboard.md
├── src/
│   ├── keycloak-spi/           ← Custom Keycloak protocol mapper (Java)
│   ├── als-auth/               ← ALS Auth Service (Python/FastAPI)
│   ├── als-logging/            ← ALS Logging Service (Python/FastAPI)
│   ├── als-settlement/         ← Settlement batch script (Python)
│   ├── network-discovery/      ← Network Discovery Service (Python/FastAPI)
│   ├── wordpress-plugin/       ← newshare-network WordPress plugin (PHP)
│   └── dashboard/              ← User Dashboard (React/TypeScript/Vite)
├── infra/
│   ├── vps1/                   ← Docker Compose + Nginx for Home Base VPS
│   ├── vps2/                   ← Docker Compose + Nginx for ALS VPS
│   └── sql/                    ← Database migration scripts
└── research/
```

## Prototype Architecture — LIVE as of Aug 11, 2026

Running on **two Hetzner cloud servers in Falkenstein** (~$15.48/mo total),
AlmaLinux 10, CSF firewall, Apache reverse proxy, Docker Compose:

- **VPS 1** (`auth.itega.org`): Keycloak 26.x (two realms) + PostgreSQL 16 + two Retail Agents
- **VPS 2** (`als.itega.org`): FastAPI services + TimescaleDB + React dashboard

Live hostnames: `auth`, `agent-c`, `agent-demo` (VPS 1); `als`, `network`,
`dashboard` (VPS 2) — all under `itega.org`, all on Let's Encrypt with automated
renewal.

**See `docs/vps-setup-record.md`** for exactly how these were built, including
the failures worth not repeating (Alma's missing kernel modules, CSF's dead
download host, the CSF/Docker iptables conflict, Keycloak rejecting JSON
comments).

**The Retail Agent runs on the home base host, never the ITEGA host.** It holds
the markup ratio and decides purchases; ITEGA may see neither. This is an
architectural rule, not a deployment convenience.

Publishers A and B are `barharbor.info` and `northberkshire.org` — two
separately-branded local news sites on different domains, seeded with demo
articles. Publisher C is **not** a WordPress site: it is the reader's home base,
a Keycloak realm on VPS 1. See `docs/publisher-sites.md`.
Settlement is **simulated only** — reports generated, no real money moves.

## VPS Resource Estimates

These estimates are based on initial component sizing. Revisit once code is running under real load.

**VPS 1 — Home Base IdSP (4GB RAM / 2 vCPU / $24/mo):**

| Process | Estimated RAM | Notes |
|---------|---------------|-------|
| Keycloak JVM (`-Xmx768m`) | 800-900 MB | Java; idles ~500MB, spikes to 1.2GB+ under load |
| PostgreSQL 16 | 200-300 MB | Two databases: `keycloak` + `newshare_profiles` |
| OS + Nginx | ~300 MB | Ubuntu 24.04 baseline |
| **Total idle** | **~1.3-1.5 GB** | ~2.5 GB headroom on 4GB droplet |

Keycloak is the bottleneck. A 2GB droplet ($12/mo) would work with `-Xmx512m` for light demo use but leaves almost no headroom. 4GB is the safe choice.

**VPS 2 — ALS Services (4GB RAM / 2 vCPU / $24/mo):**

| Process | Estimated RAM | Notes |
|---------|---------------|-------|
| PostgreSQL + TimescaleDB | 200-300 MB | Two databases: `als_logs` + `als_settlement` |
| FastAPI Auth Service | 50-80 MB | Python; lightweight async |
| FastAPI Logging Service | 50-80 MB | Python; lightweight async |
| Nginx + static files | ~30 MB | Dashboard + Network Discovery |
| OS | ~300 MB | Ubuntu 24.04 baseline |
| **Total idle** | **~650-800 MB** | Significantly overprovisioned at 4GB |

VPS 2 could run on a 2GB droplet ($12/mo) and be comfortable. Keeping 4GB for now gives room if TimescaleDB grows or if we add services later. Can downsize to save ~$12/mo.

**Cheaper alternative:** VPS 1 at 4GB ($24) + VPS 2 at 2GB ($12) + domain ($1) = **~$37/mo**.

## Technology Stack (for code)

When building components, use these technologies:
- **Home Base IdSP:** Keycloak 26.x (Quarkus) + PostgreSQL 16. JVM tuned to `-Xms256m -Xmx768m` for 4GB VPS.
- **Keycloak SPI:** Custom Java protocol mapper (~120 lines) for `networkUserId` claim format. Extends `AbstractOIDCProtocolMapper`.
- **ALS Auth:** Python 3.12 + FastAPI. Issues its own `sessionToken` (RS256-signed JWT). Routes auth through Keycloak.
- **ALS Logging:** Python 3.12 + FastAPI. Writes to TimescaleDB `access_events` hypertable. Append-only.
- **ALS Settlement:** Python 3.12 batch script. Runs via weekly cron. Queries TimescaleDB, generates CSV/JSON reports.
- **Publisher Plugin:** WordPress plugin (PHP 8.1+) with OIDC RP flow through ALS (not directly to Keycloak).
- **User Dashboard:** React 19 + TypeScript + Vite + Tailwind CSS 3.
- **Content Tagging:** JSON-LD in HTML (`<script type="application/ld+json">`)
- **Infrastructure:** Docker Compose, Nginx with Let's Encrypt TLS, Cloudflare DNS.

## Key API Contracts

ALS Auth Service endpoints:
- `GET /auth/authorize` — initiates OIDC flow; resolves the visitor's home base or presents the chooser
- `GET /auth/select-home-base` — handles the chooser answer (name or Publishing Member ID)
- `GET /auth/callback` — handles OIDC callback, issues sessionToken
- `POST /auth/validate` — validates ALS-issued sessionTokens
- `GET /auth/home-bases` — lists certified home bases (sourced from Network Discovery)

ALS Logging Service endpoints:
- `POST /log/event` — ingests access events (fire-and-forget from publishers)
- `GET /log/report/home-base/{id}` — full clickstream for a home base
- `GET /log/report/publisher/{id}` — aggregated totals only for a publisher

Network Discovery Service endpoints:
- `GET /discovery/home-bases` — all certified home bases
- `GET /discovery/home-bases/resolve` — resolve a visitor to a home base (by id, name, or IP hint)
- `GET /discovery/home-bases/{id}` — a single certified home base
- `GET /discovery/publishers` — all certified publishers
- `GET /.well-known/webfinger` — WebFinger (RFC 7033) home-site discovery
- `GET /.well-known/newshare-network` — network-wide discovery document

sessionToken JWT claims: `iss`, `sub`, `aud`, `exp`, `iat`, `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `sessionId`

## Wholesale vs. retail — get this right

- `pageClass` **is** the wholesale price: what the publisher (Rights Owner) asks and is owed.
- `pageClass * markupRatio` is the **retail** price: what the home base (Retail Agent) bills its own user.
- **Only wholesale is settled through the ALS.** The markup is the home base's margin and never reaches the publisher.
- **Never disclose `markupRatio` or retail totals to publishers.** Per the pricing rules the Rights Owner does not need to know the markup and may not be permitted to.

Settlement previously had this inverted (crediting publishers the retail amount); see `docs/demo-script-gap-analysis.md`.

## Naming Conventions

- The consumer-facing brand is **"Newshare"** (or "Newshare Network")
- The governing body is **"ITEGA"**
- The technical/developer-facing brand can be **"NewsSSO"**
- **Publishers are named by letter: A, B, C.** Bill's demo script also calls them
  "Publisher 1/2/3" in places — those are the same parties (C == 3, A/B == 1/2), an
  artefact of the Definitions section being written before the later steps. Letters
  win everywhere: code, docs, registry data, demo copy.
- Use `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `pageClass`, `markupRatio` for field names (camelCase, per the spec)
- Use `content_access`, `authentication`, `ad_view`, `subscription_credit`, `reward`, `logout` for event type enums
- Use `sessionId` for the ALS-issued session identifier claim in JWTs

## Key People

- **Bill Densmore** — ITEGA Founder & Interim Executive Director
- **Richard Lerner** — Clickshare CEO, co-inventor, lead architect (Carnegie Mellon PhD)
- **Sho Rust** — PubGen.AI CEO, technical operator for Missouri pilot
- **Matt Baya** — Project participant / reviewer
- **Drummond Reed** — Decentralized identity pioneer, Chief Trust Officer at Evernym, peer reviewer. Recommends VTN/DID evolution path.
- **Don Marti** — Longtime ITEGA advisor, open source/web standards expert, peer reviewer. Recommends simplifying to minimum demo-able version.
- **Glen Gerbush** — Developer Bill consulted. Argued the AI-generated codebase should be discarded rather than extended. Bill overrode this ("a bird in the hand") and chose to build on `src/` for Aug 25.

## Current work: the Aug 25 demo

**Start by reading `docs/STATUS.md`** — it is the living handoff document: what is
built, what is verified, what comes next in priority order, and the decisions already
settled with Bill. Keep it current as work lands.

Work is driven by Bill's demo script for the RJI/ITEGA roundtable on **Aug 25, 2026**.
The script lives in `reference/` (gitignored) and Bill revises it — check for the newest
`ITEGA-RJI-demo-script-*.md` before building. `docs/demo-script-gap-analysis.md` tracks
what is built, what is missing, and Bill's answers to the open questions.

**Build it really working.** A simulated or narrated demo is the fallback, not the goal.

### Test before you claim

Run both suites before showing the system to anyone, or writing that it works:

```bash
infra/smoke-test.sh      # 28 checks: every public endpoint, both realms, both sites
infra/journey-test.py    # 12 checks: the reader's journey, end to end
infra/logout-test.py     # 19 checks: both sign-out scopes actually differ
infra/totp-test.py       # 14 checks: two-factor really challenges, both realms
```

Deploy the publisher plugin only with `infra/deploy-publisher-plugin.sh <site>`
(or `all`). It lints locally, ships the plugin as a unit, checks real pages
afterwards and rolls back if the site stops answering. Copying single files with
`scp` is what took barharbor.info down; there is no longer a supported way to do
it. `NEWSHARE_DEPLOY_FORCE_FAIL=1` rehearses the rollback against a healthy
site.

These exist because the sign-in path was broken for weeks and nobody knew. When
it was finally walked start to finish it turned up **seven separate faults**, any
one of which stopped a reader dead — a missing PKCE challenge, a GET-only
callback the ALS posted to, a parameter named two different things on the two
sides, a wrong authorize path, a scope no home base defines, an
`OpenSSLAsymmetricKey` cached into a transient, and a token signed without a
`kid`. Five more were found elsewhere, including publishers never filing the
purchases they were owed for.

Every one of them looked healthy from the hop before it. Checking that a service
returns 200 proves almost nothing about whether a person can get through it, so:

- **Assert on the result, not the redirect.** A 302 towards a login page is not
  a login.
- **Walk the whole path** as a reader does, from the article to the session, not
  from the API inwards.
- **Log defects as GitHub issues** with cause, fix and verification, then close
  them with what proved the fix. `gh issue list --state all` is the record.

The ALS base URL is the **host only** — the flow lives under `/auth/`. Two
separate codebases got this wrong independently.

**This repository is public** — Bill's Editor & Publisher column links to it directly.
Correspondence and source documents belong in `reference/`, never in a commit.

## Important Constraints

- The pilot targets **3-5 independent Missouri newspapers** via MPA
- Budget is **$400,000 over 18 months**
- Infrastructure budget is **$300-$500/month** for a single cloud VM
- The pilot is a **proof-of-concept**, not a scale deployment
- Success = **50+ real users** complete cross-publisher authentication
- Phase 2 (UDEX — User Data Exchange) is explicitly deferred; do not build it now

## Evolution Path: Decentralized Identity

The current OIDC-based architecture is a pragmatic starting point. Peer review (Drummond Reed, Feb 2026)
identified a future migration path to **Verifiable Trust Networks (VTNs)** based on W3C DIDs, Verifiable
Credentials, and Trust Over IP (ToIP) standards. Key points:

- The four-party model maps one-to-one onto ToIP's VTN concept (ITEGA → VTN Governance, Home Base → Credential Issuer, Publisher → Verifier, ALS → Trust Registry)
- Current architecture already includes bridge decisions: PPID, no central DB, W3C VCs in protocol stack, no cookies, JWT tokens (same format as JWT-VC)
- Phase 1 = OIDC pilot (ship now). Phase 2+ = migrate to DID/VC as ecosystem matures.
- See `docs/peer-review-synthesis.md` for full analysis and migration roadmap.
- The **First Person Cooperative** and **Content Authenticity Initiative** (Adobe/C2PA) are potential partners for a media-industry VTN.

## Source Documents

The definitive technical reference is `claude-itega-newshare-tech-spec-02-22-26b-1110pest.pdf`
in `docs/source-pdfs/`. When in doubt about architecture, protocol choices, or field names,
refer to that document. The funder brief and chat transcript provide additional business context.
