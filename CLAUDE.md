# CLAUDE.md — Project Instructions for Claude Code

## Project: ITEGA / Newshare Network

This repository contains the technical review, planning documents, and (eventually) reference
implementation code for the Newshare Network, governed by ITEGA.

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
└── research/
```

## Technology Stack (for code)

When building components, use these technologies per the spec:
- **Home Base IdSP:** Keycloak or Authentik + PostgreSQL 16 + Redis 7
- **ALS Auth:** Python (FastAPI) or Node.js (Fastify) sidecar to Keycloak
- **ALS Logging:** TimescaleDB (PostgreSQL extension) + async Python/Node daemon
- **ALS Settlement:** Python batch script + Stripe Connect API
- **Publisher Plugin:** WordPress plugin (PHP 8.1+) with OIDC RP
- **User Dashboard:** React 19 + TypeScript + Vite + Tailwind CSS
- **Content Tagging:** JSON-LD in HTML (`<script type="application/ld+json">`)

## Naming Conventions

- The consumer-facing brand is **"Newshare"** (or "Newshare Network")
- The governing body is **"ITEGA"**
- The technical/developer-facing brand can be **"NewsSSO"**
- Use `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `pageClass`, `markupRatio` for field names (camelCase, per the spec)
- Use `content_access`, `ad_view`, `subscription_credit`, `reward` for event type enums

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
