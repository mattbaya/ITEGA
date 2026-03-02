# Response to Bill Densmore — Peer Review Incorporated

*March 2026*

Bill,

Here's a summary of what's in the GitHub repository, how we've incorporated the peer review feedback from Drummond Reed and Don Marti, and the recommended path forward.

---

## What's in the Repository

The ITEGA/Newshare GitHub repo (`github.com/[repo]`) now contains:

### Technical Specification and Plans
- **7 detailed implementation plans** (`plans/` directory) covering every component: Home Base IdSP, ALS Auth Service, ALS Logging Service, ALS Settlement Service, Publisher WordPress Plugin, Network Discovery Service, and User Dashboard
- **System architecture overview** with protocol stack, deployment diagrams, and budget breakdowns

### Working Prototype Code
- **~3,400 lines of source code** (`src/` directory) implementing all 6 components:
  - Custom Keycloak protocol mapper (Java) for Newshare `networkUserId` claim format
  - ALS Auth Service (Python/FastAPI) — token validation and OIDC flow routing
  - ALS Logging Service (Python/FastAPI) — event ingestion into TimescaleDB
  - ALS Settlement Service (Python) — batch settlement report generation
  - WordPress plugin (PHP) — "Network Login" button, OIDC Relying Party, content access control via NetworkGroupId
  - User Dashboard (React/TypeScript) — session, reading history, and balance display

### Deployment Infrastructure
- **Docker Compose configurations** for two VPS instances (~$49/month on DigitalOcean)
- **Nginx configurations** with Let's Encrypt TLS
- **Database migration scripts** for PostgreSQL and TimescaleDB

### Documentation
- **Comprehensive README** with the full Visa analogy, Susan-reads-the-news walkthrough, and competitive landscape
- **CLAUDE.md** project instructions for AI-assisted development
- **Source PDFs** — your original documents preserved in `docs/source-pdfs/`

---

## How Peer Review Feedback Has Been Incorporated

We received feedback from two expert reviewers with very different — and complementary — perspectives:

### Drummond Reed (received Feb 27)
Drummond argued that OIDC-based federated identity is being superseded by decentralized identity (DIDs, Verifiable Credentials, Trust Over IP) and recommended ITEGA consider becoming a Verifiable Trust Network (VTN) through the First Person Cooperative. He noted that ITEGA's governing-not-operating model maps naturally to VTN governance.

### Don Marti (received Mar 2)
Don recommended simplifying to the minimum demo-able version, warned that independent publishers have extremely brittle tech stacks, and suggested focusing on what works with tools already on publisher sites.

### What We Did

1. **Created a full peer review synthesis** — `docs/peer-review-synthesis.md` — with side-by-side comparison, analysis of agreements and divergences, and a recommended path forward.

2. **Updated the system architecture plan** — added a "Future Evolution: Decentralized Identity" section to `plans/00-system-architecture-overview.md` documenting the DID/VTN direction and migration path.

3. **Identified bridge design decisions** — documented how the current architecture already aligns with decentralized principles (PPID, no central DB, VCs in protocol stack, no cookies) and how each design choice keeps VTN migration feasible.

4. **Updated README and project documentation** — added peer review feedback summary and evolution path sections.

---

## Mapping to Bill's 5 Core Requirements

In your March 2 email to Graf, Rick, and Sho, you distilled the goal to five essentials. Here's how the prototype addresses each:

| Bill's Requirement | Prototype Status |
|-------------------|-----------------|
| **1. Network user authentication service with plurality of independent "user owners"** | **Built.** Keycloak Home Base (IdSP) + ALS Auth Service. Federated model supports multiple independent home bases, each owning their users. |
| **2. Network logging service for chargeable content accesses** | **Built.** ALS Logging Service writes to TimescaleDB. Every content access event is logged with opaque user ID, publisher ID, page class, and timestamp. |
| **3. At least two independent publisher web services** | **Ready.** WordPress plugin installs on any WordPress site. Designed for 3-5 MPA newspapers. Plugin handles OIDC flow and NetworkGroupId access control. |
| **4. Connection to bank ACH for charging and paying** | **Simulated.** Settlement script generates reports showing debits/credits. Real ACH (via Stripe Connect) is a configuration step, not a code change. |
| **5. Publisher/user code to negotiate payment and access terms** | **Partially built.** Wholesale-retail pricing model is in the architecture (publishers set `pageClass`, home bases set `markupRatio`). Real-time negotiation UI is Phase 2. |

The prototype covers requirements 1-3 fully, requirement 4 in simulation, and requirement 5 at the data-model level. This is the "minimum demo-able version" that both Don Marti and your own email describe.

---

## Recommended Strategy: Dual-Track

Both reviewers are right — and their advice is complementary:

### Track 1: Ship the Missouri Pilot (Now)
Follow Don's advice. The current OIDC-based prototype is the right approach for the Missouri pilot. It uses proven technology, works with existing WordPress sites, and can demonstrate the full four-party model with real publishers and real users. Simplify where possible to get to the minimum demo-able version.

This directly addresses the question you raised for today's meeting with Rick, Graf, and Sho: "How do we move quickly to code and operate?" The answer: the prototype code exists, it needs deployment and testing with real publisher sites.

### Track 2: Plan the VTN Evolution (Parallel)
Follow Drummond's advice. Engage with the First Person Cooperative about a news-industry Verifiable Trust Network. The pilot validates the business model and governance; the underlying authentication protocol can evolve. Key insight: **the four-party model maps almost one-to-one onto ToIP's VTN concept.**

### Why This Works
- The four-party model is protocol-agnostic — it works with OIDC today and DIDs tomorrow
- The current architecture already uses pairwise pseudonymous IDs, has no central identity database, includes W3C Verifiable Credentials, and avoids cookies — all aligned with decentralized principles
- A working pilot proves the business and governance model, which is the hard part
- ITEGA's governing-not-operating role is exactly what VTN governance looks like
- Drummond's VTN approach and the current OIDC prototype are **not in conflict** — they operate on different timelines and the pilot validates what matters most: the governance model, publisher participation, and user experience

---

## Next Steps

### Immediate (Pilot Track)
1. Deploy prototype to DigitalOcean VPS instances
2. Install WordPress plugin on participating MPA newspaper sites
3. Onboard 3-5 Missouri newspapers and begin user registration
4. Run the cross-publisher authentication demo end-to-end

### Parallel (VTN Track)
1. Schedule a call with Drummond Reed to explore First Person Cooperative partnership
2. Connect with the Content Authenticity Initiative (Adobe/C2PA) — Drummond mentioned they're starting VTN discussions for media
3. Document the migration path from OIDC to DID-based authentication

### Open Questions
1. **Drummond engagement:** Is there interest in a formal conversation between ITEGA and the First Person Cooperative about a news-industry VTN?
2. **Pilot scope:** Should we strip the pilot down further per Don's advice? What's the absolute minimum: just cross-publisher login + event logging, without settlement?
3. **PubGen.AI coordination:** Has Sho Rust reviewed the WordPress plugin approach? His input on publisher integration is critical.
4. **Funding status:** Does the dual-track strategy (pilot now + VTN planning) affect the funder brief or budget?

---

## Key Documents

| Document | Location |
|----------|----------|
| Peer Review Synthesis | [`docs/peer-review-synthesis.md`](peer-review-synthesis.md) |
| System Architecture Overview | [`plans/00-system-architecture-overview.md`](../plans/00-system-architecture-overview.md) |
| Full README | [`README.md`](../README.md) |
| Source Code | [`src/`](../src/) |
| Infrastructure | [`infra/`](../infra/) |

---

*Prepared for Bill Densmore, ITEGA. March 2026.*
