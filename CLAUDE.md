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
│   └── source-pdfs/            ← Original documents from Bill Densmore
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
│   ├── wordpress-plugin/       ← newshare-network WordPress plugin (PHP)
│   └── dashboard/              ← User Dashboard (React/TypeScript/Vite)
├── infra/
│   ├── vps1/                   ← Docker Compose + Nginx for Home Base VPS
│   ├── vps2/                   ← Docker Compose + Nginx for ALS VPS
│   └── sql/                    ← Database migration scripts
└── research/
```

## Prototype Architecture

The prototype runs on **two DigitalOcean 4GB droplets** (~$49/mo total):

- **VPS 1** (`auth.newshare.example`): Keycloak 26.x + PostgreSQL 16 — Home Base IdSP
- **VPS 2** (`als.newshare.example`): FastAPI services + TimescaleDB + React dashboard + Nginx

WordPress plugin installs on Matt's existing 4+ WordPress sites (no additional servers).
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
- `GET /auth/authorize` — initiates OIDC flow, redirects to home base
- `GET /auth/callback` — handles OIDC callback, issues sessionToken
- `POST /auth/validate` — validates ALS-issued sessionTokens
- `GET /auth/home-bases` — lists certified home bases

ALS Logging Service endpoints:
- `POST /log/event` — ingests access events (fire-and-forget from publishers)
- `GET /log/report/home-base/{id}` — full clickstream for a home base
- `GET /log/report/publisher/{id}` — aggregated totals only for a publisher

sessionToken JWT claims: `iss`, `sub`, `aud`, `exp`, `iat`, `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `sessionId`

## Naming Conventions

- The consumer-facing brand is **"Newshare"** (or "Newshare Network")
- The governing body is **"ITEGA"**
- The technical/developer-facing brand can be **"NewsSSO"**
- Use `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `pageClass`, `markupRatio` for field names (camelCase, per the spec)
- Use `content_access`, `authentication`, `ad_view`, `subscription_credit`, `reward`, `logout` for event type enums
- Use `sessionId` for the ALS-issued session identifier claim in JWTs

## Key People

- **Bill Densmore** — ITEGA Founder & Interim Executive Director
- **Richard Lerner** — Clickshare CEO, co-inventor, lead architect (Carnegie Mellon PhD)
- **Sho Rust** — PubGen.AI CEO, technical operator for Missouri pilot
- **Matt Baya** — Project participant / reviewer

## Important Constraints

- The pilot targets **3-5 independent Missouri newspapers** via MPA
- Budget is **$400,000 over 18 months**
- Infrastructure budget is **$300-$500/month** for a single cloud VM
- The pilot is a **proof-of-concept**, not a scale deployment
- Success = **50+ real users** complete cross-publisher authentication
- Phase 2 (UDEX — User Data Exchange) is explicitly deferred; do not build it now

## Source Documents

The definitive technical reference is `claude-itega-newshare-tech-spec-02-22-26b-1110pest.pdf`
in `docs/source-pdfs/`. When in doubt about architecture, protocol choices, or field names,
refer to that document. The funder brief and chat transcript provide additional business context.
