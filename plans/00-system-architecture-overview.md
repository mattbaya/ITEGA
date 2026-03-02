# Newshare Network — System Architecture Overview

*Aligned with: Newshare Network Technical Architecture and Specification v1.0 Draft, February 2026*

## The Four-Party Model

The Newshare Network is **not** a centralized platform. It is a federated four-party network
analogous to the credit card system (Visa/Mastercard). ITEGA governs but does not operate.

```
                    ┌─────────────────────────────────────────────┐
                    │           ITEGA (Governing Authority)        │
                    │  Sets rules, certifies participants,         │
                    │  enforces standards. Does NOT operate.       │
                    └──────────────────┬──────────────────────────┘
                                       │ Certifies & Licenses
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
┌──────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│  2. HOME BASE     │    │ 4. ALS (Auth/Logging/ │    │  3. PUBLISHER     │
│  (IdSP)           │    │    Settlement Service)│    │  (Content         │
│                   │    │                      │    │   Provider)       │
│ • OIDC Provider   │    │ • Token validation   │    │ • OIDC Relying    │
│ • User accounts   │    │ • Event logging      │    │   Party           │
│ • Profile store   │    │ • ACH settlement     │    │ • WordPress       │
│ • PPID generation │    │ • Usage reports      │    │   plugin          │
│ • Billing/retail  │    │ • No PII access      │    │ • Content + RSL   │
│   markup          │    │                      │    │   tagging         │
│                   │    │ Knows users ONLY by  │    │                   │
│ ONLY party that   │    │ opaque networkUserId │    │ Accepts users     │
│ knows user's      │    │                      │    │ from ANY home     │
│ real identity     │    │                      │    │ base without      │
│                   │    │                      │    │ re-registration   │
└────────┬─────────┘    └──────────┬───────────┘    └────────┬─────────┘
         │                         │                          │
         │         ┌───────────────┼──────────────┐           │
         │         │               │              │           │
         ▼         ▼               ▼              ▼           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                     1. END USER (Reader)                     │
    │  • Registers once at home base                               │
    │  • Visits any publisher on the network                       │
    │  • Known only by opaque pairwise pseudonymous ID             │
    │  • Different ID at each publisher (no cross-site tracking)   │
    └──────────────────────────────────────────────────────────────┘
```

## Authentication Flow (8 Steps)

```
User → Publisher B (no account) → "Network Login" → Home-site discovery
  → Redirect to Home Base → User authenticates → Home Base generates
    PPID + NetworkGroupId → Redirect back through ALS → Publisher B
      maps NetworkGroupId → serves content → ALS logs event
        → Settlement (weekly batch via ACH)
```

| Step | Action |
|------|--------|
| 1 | User clicks content link at Publisher B (not registered there) |
| 2 | Publisher B detects no session, presents "Network Login" option |
| 3 | User selects Network Login; home-site discovery (cookie or manual selection) |
| 4 | Network server redirects to user's Home Base (IdSP) |
| 5 | Home Base authenticates user, generates/retrieves pairwise networkUserId |
| 6 | Home Base passes networkUserId + NetworkGroupId to network server → Publisher B |
| 7 | Publisher B maps NetworkGroupId to access controls, serves content, logs to ALS |
| 8 | Settlement: ALS aggregates logs, computes debits/credits, initiates ACH transfers |

## Server/Component Inventory

| # | Component | What It Is | Operator | Public-Facing |
|---|-----------|------------|----------|---------------|
| 01 | Home Base (IdSP) | OIDC Provider + user profile store + billing | Any certified publisher/ISP/library | Yes (to their users) |
| 02 | ALS — Auth Service | Real-time token validation | Licensed ALS operator (e.g. Clickshare) | Yes (API) |
| 03 | ALS — Logging Service | Event logging (time-series) | Licensed ALS operator | Internal |
| 04 | ALS — Settlement Service | Batch ACH processing | Licensed ALS operator | Internal |
| 05 | Publisher Plugin | WordPress OIDC RP + NetworkGroupId mapping | Each publisher | Yes (on publisher site) |
| 06 | Network Discovery | OIDC Discovery endpoint + certified member directory | ITEGA | Yes |
| 07 | User Dashboard | React app showing session, publishers visited, balance | Demo for pilot | Yes |

## Key Architectural Distinctions from Typical SSO

| Typical SSO (Google, etc.) | Newshare Network |
|---------------------------|------------------|
| Platform owns user identity | Home base owns user identity |
| Same user ID across all sites | **Different pseudonymous ID per publisher (PPID)** |
| Cookies for session tracking | **Token via HTTP headers, no cookies** |
| Platform sets all prices | **Wholesale-retail pricing: publishers set wholesale, home bases set retail markup** |
| Central identity database | **No central identity database; distributed like DNS** |
| Profit to platform | **Profit to operators and publishers; ITEGA covers governance costs only** |

## Protocol Stack

| Function | Protocol/Standard |
|----------|------------------|
| Core SSO federation | OpenID Connect 1.0 (Authorization Code Flow) |
| Token format | JSON Web Token (JWT, RFC 7519) |
| Home-site discovery | OIDC Discovery + WebFinger (RFC 7033) |
| Pairwise user IDs | OIDC PPID (Pairwise Pseudonymous Identifiers) |
| Rich identity claims | W3C Verifiable Credentials (VC Data Model 2.0) |
| Token encryption | JSON Web Encryption (JWE, RFC 7516) |
| Subscriber tier encoding | Custom NetworkGroupId bitmask claim in OIDC ID Token |
| User profile attributes | Schema.org/Person + Internet2 eduPerson |
| Content rights tagging | Really Simple Licensing (RSL) standard |
| Transport security | TLS 1.3 mandatory |

## NetworkGroupId Bitmask

| Bit Value | Access Level |
|-----------|-------------|
| 0 | Anonymous (pre-registration meter) |
| 1 | Group Account (IP-based or access-key) |
| 2 | Registered (logged in, individual account) |
| 4 | Print Subscriber |
| 8 | Digital / Web Subscriber |
| 16 | Data / Special Content Subscriber |
| 1024 | Complimentary Subscriber |
| 2048 | Controlled (free) Subscriber |
| 4096 | Paid Subscriber |
| 8192 | Trial Subscriber |
| 16384 | Site / Group Subscriber (corporate, university, library) |

Bits are combined: Paid (4096) + Print (4) = NetworkGroupId 4100.

## Recommended Technology Stack (from spec Section 5.2)

| Component | Recommended Approach |
|-----------|---------------------|
| OIDC / Identity Provider | **Keycloak** (Java, Apache 2.0) or **Authentik** (Python/Go) |
| Home Base User Profile Store | PostgreSQL + schema from Clickshare Customer Profile Server. **Apache Unomi** as candidate profile management layer |
| ALS — Auth Service | Custom lightweight service on chosen OIDC provider's token endpoint. Runs as sidecar to Keycloak/Authentik |
| ALS — Logging Service | **TimescaleDB** (PostgreSQL extension) or **ClickHouse**. Async daemon writes Extended Common Log Format records |
| ALS — Settlement Service | **Python or Node.js** batch process. **Stripe Connect** API for ACH. Generates settlement reports |
| Publisher Integration | **WordPress plugin** implementing OIDC Relying Party + NetworkGroupId mapping |
| Content Rights Tagging | **RSL** standard metadata embedded in article HTML/JSON-LD |
| Network Discovery | OIDC Discovery endpoint at well-known ITEGA URL |
| Demo / User Dashboard | **React** app showing session, publishers visited, account balance |

## Deployment Architecture (Missouri Pilot)

```
┌─────────────────────────────────────────────────────────┐
│                  Cloud VM (AWS/GCP/DigitalOcean)         │
│                  $300–$500/month                         │
│                                                         │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ Keycloak or      │  │ PostgreSQL + TimescaleDB      │  │
│  │ Authentik        │  │ • User profiles               │  │
│  │ (IdSP + ALS Auth)│  │ • Event logs                  │  │
│  └─────────────────┘  │ • Settlement data              │  │
│                        └──────────────────────────────┘  │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ Python Settlement│  │ React User Dashboard          │  │
│  │ (weekly cron)    │  │ (demo consumer experience)    │  │
│  └─────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ MO Newspaper │ │ MO Newspaper │ │ MO Newspaper │
    │ WordPress    │ │ WordPress    │ │ WordPress    │
    │ + Plugin     │ │ + Plugin     │ │ + Plugin     │
    └──────────────┘ └──────────────┘ └──────────────┘
       3–5 participating Missouri newspapers via MPA
```

**Pilot scope:** 2–3 developers, 4–6 months build, 18-month total program
**Budget:** $400,000 (funder brief) / $273K–$385K (tech spec estimate)
**Success criteria:** 50+ real users complete cross-publisher authentication flow

## Budget Summary (from Funder Brief)

| Item | Amount |
|------|--------|
| Technical Development (2 devs, 12 months) | $180,000 |
| Project Director | $75,000 |
| Project Coordination (Densmore, 0.33 FTE) | $35,000 |
| Richard Lerner / Technical Architecture | $30,000 |
| Cloud Infrastructure ($300/mo x 18 months) | $5,400 |
| Publisher Integration Support | $15,000 |
| Legal | $15,000 |
| Travel and Convenings | $18,000 |
| Evaluation and Reporting | $12,000 |
| Contingency (10%) | $19,600 |
| **TOTAL** | **$400,000** |

## Pilot Partners

| Role | Partner |
|------|---------|
| Institutional Host | Donald W. Reynolds Journalism Institute (RJI), University of Missouri |
| Industry Convener | Missouri Press Association (MPA) |
| Technical Operator | PubGen.AI (Sho Rust, CEO) — Cape Girardeau, MO |
| Technical Consultant | Clickshare Service Corp. (Richard Lerner, CEO) — Amherst, MA |
| Governing Authority | ITEGA |
| Participating Publishers | 3–5 independent Missouri newspapers via MPA |

---

## Future Evolution: Decentralized Identity

*Based on peer review feedback from Drummond Reed (February 2026) and ongoing developments in the Trust Over IP (ToIP) and W3C Decentralized Identifier (DID) ecosystems.*

### Context

Drummond Reed — Chief Trust Officer at Evernym, co-author of the Respect Trust Framework, and a leading figure in decentralized identity standards — reviewed the Newshare Network technical documents in February 2026. His assessment: while OIDC remains viable today, the identity landscape is shifting rapidly toward **decentralized digital identity** based on digital wallets, Verifiable Credentials (VCs), and Decentralized Identifiers (DIDs). This shift is being accelerated by the AI revolution — AI agents don't use browsers or OIDC, and demand infrastructure that scales in a decentralized manner.

Reed specifically recommended ITEGA consider becoming a **Verifiable Trust Network (VTN)** through the **First Person Cooperative (FPC)**, which is building VTNs across multiple sectors (open source, event communities, cooperatives, universities, cities) and plans to approach the **Content Authenticity Initiative** (Adobe/C2PA) about a media-industry VTN.

### How the Four-Party Model Maps to ToIP's VTN Concept

The Newshare four-party model maps nearly one-to-one onto the ToIP Verifiable Trust Network architecture:

| Newshare Role | ToIP/VTN Role | Function |
|--------------|---------------|----------|
| **ITEGA** (Governing Authority) | **VTN Governance Authority** | Sets rules, certifies participants, enforces standards |
| **Home Base** (IdSP) | **Credential Issuer / Wallet Provider** | Issues verifiable credentials to users; operates digital wallet infrastructure |
| **Publisher** (Content Provider) | **Verifier / Relying Party** | Requests and verifies credentials for content access |
| **ALS** (Auth/Logging/Settlement) | **Trust Registry + Verification Service** | Maintains registry of trusted issuers; validates credential presentations; logs events |
| **End User** | **Holder** | Holds verifiable credentials in a digital wallet; presents them to publishers |

The key architectural difference: in the VTN model, credentials are presented directly from the user's wallet to the publisher (or through the ALS as a proxy verifier), eliminating OIDC redirect chains. This also enables native AI agent authentication.

### Bridge Decisions Already in Current Architecture

The current OIDC-based architecture already incorporates several design decisions that align with decentralized identity principles and keep the migration path open:

- **Pairwise Pseudonymous Identifiers (PPID):** Each user has a different opaque ID per publisher — this is exactly the privacy model that VCs enforce through selective disclosure.
- **No central identity database:** The network is distributed like DNS, consistent with decentralized identity architecture.
- **W3C Verifiable Credentials in protocol stack:** VC Data Model 2.0 is already specified for rich identity claims. This is the core credential format in ToIP/VTN.
- **JWT tokens with RS256 signing:** JWTs are also the serialization format for Verifiable Credentials (JWT-VC). Same token format, different issuance model.
- **PII never leaves the home base:** Data minimization is architectural, not policy — consistent with wallet-based credential presentation.
- **No cookies / header-based auth:** Aligns with wallet-based credential presentation. No browser dependency.
- **JSON-LD content tagging (RSL):** Aligns with Content Authenticity Initiative (C2PA) provenance metadata.
- **Home Base as sole identity authority:** Maps to the "credential issuer / wallet provider" concept in VTN.
- **ALS as neutral validator:** Maps to the ToIP "verifier" and "trust registry" roles.

### Phase 2+ Migration Path: OIDC to DID-Based Authentication

| Phase | Auth Model | Changes Required |
|-------|-----------|-----------------|
| **Phase 1** (Missouri Pilot) | OIDC Authorization Code Flow via ALS | None — ship as designed |
| **Phase 1.5** (Bridge) | OIDC + optional VC presentation | Home bases issue VCs alongside OIDC tokens; publishers accept either format |
| **Phase 2** (Hybrid) | DID-based auth preferred, OIDC fallback | Users with digital wallets use VC presentation; legacy users fall back to OIDC; ALS accepts both |
| **Phase 3** (Full VTN) | DID/VC native | All auth via verifiable credential presentation; OIDC deprecated; home bases operate as credential issuers |

### Key Standards to Track

- **W3C Decentralized Identifiers (DIDs)** — [w3.org/TR/did-core](https://www.w3.org/TR/did-core/)
- **W3C Verifiable Credentials Data Model 2.0** — [w3.org/TR/vc-data-model-2.0](https://www.w3.org/TR/vc-data-model-2.0/)
- **Trust Over IP (ToIP) Foundation** — [trustoverip.org](https://trustoverip.org)
- **First Person Project / First Person Cooperative** — [firstperson.global](https://firstperson.global)
- **Content Authenticity Initiative (C2PA)** — [c2pa.org](https://c2pa.org)
- **Agentic AI Foundation (Linux Foundation)** — AI agent interoperability standards (A2A, MCP, AGNTCY)

### Recommendation

**Ship the OIDC pilot now.** The current architecture is sound, uses proven technology, and demonstrates the full four-party model. In parallel, engage with Drummond Reed and the First Person Cooperative about a news-industry VTN. The pilot validates the governance and business model; the authentication protocol can evolve. See `docs/peer-review-synthesis.md` for the full analysis.
