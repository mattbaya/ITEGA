# Peer Review Synthesis: Newshare Network Technical Architecture

*March 2026*

## Overview

In February 2026, Bill Densmore shared the Newshare Network technical documents — the Technical Architecture and Specification v1.0 Draft, funder brief, and Claude AI chat transcript — with two expert reviewers for peer assessment. This document synthesizes their feedback and recommends a path forward.

### The Reviewers

**Drummond Reed** — Decentralized identity pioneer. Chief Trust Officer at Evernym, co-author of the Respect Trust Framework (Privacy Award, 2011 European Identity Conference). Over two decades of work in Internet identity, security, privacy, and trust frameworks. Active in the W3C Decentralized Identifiers (DID) working group, Trust Over IP (ToIP) Foundation, and the newly established First Person Cooperative (FPC). Recently led sessions at the 2026 Linux Foundation Member Summit on decentralized digital identity.

**Don Marti** — Longtime ITEGA advisor. Open source and web standards expert with deep knowledge of the independent publishing ecosystem. Practical perspective on publisher technology constraints and deployment realities.

---

## Summary of Feedback

### Drummond Reed's Assessment

Drummond's core message: **the technology landscape has shifted fundamentally.** He argues that:

1. **OIDC and federated identity are being superseded** by decentralized digital identity based on digital wallets and verifiable credentials (VCs), driven by the AI revolution.
2. **AI agents demand decentralized solutions** — they don't use browsers, don't use OpenID, and need infrastructure that scales the way the Internet scales.
3. **The First Person Project and Trust Over IP (ToIP)** provide a standards-based framework for "Verifiable Trust Networks" (VTNs) that could realize ITEGA's vision of a global news network with frictionless authentication and integrated micropayments.
4. **The First Person Cooperative (FPC)** is actively building VTNs in multiple sectors (open source at Linux Foundation, event communities, cooperatives, universities, cities) and is about to approach Adobe and the Content Authenticity Initiative about a VTN for the media industry.
5. **A VTN for the news industry could fit perfectly** with ITEGA's mission and governance model.

He explicitly states this would be "a complete departure from anything in your patents" and does not use OIDC or federated identity. He recommends reading the First Person Project white paper and invited further discussion.

### Don Marti's Assessment

Don's core message: **simplify to the minimum demo-able version.** He observes that:

1. **The project as described is huge** — "lots of subtasks that look plausible but could grow as details get figured out."
2. **Independent publishers have extremely brittle tech stacks** — changes must be minimal and low-risk for publisher participation.
3. **Start from one page of an understandable project** to get a basic demo, using tools already present on publisher sites.
4. **Consider bringing in a large advertiser** as a funding source — publishers respond more readily when direct-sold advertising is involved.
5. **Focus on the minimum demo-able version** rather than the full specification.

---

## Side-by-Side Comparison

| Dimension | Drummond Reed | Don Marti |
|-----------|--------------|-----------|
| **Core recommendation** | Pivot to Verifiable Trust Networks (VTNs) via DID/VC/ToIP standards | Simplify to minimum demo-able version using existing tools |
| **View of OIDC** | Being superseded; inadequate for AI agent era | Not discussed; implicitly acceptable if it works |
| **Timeline perspective** | Forward-looking (3-5 year horizon, next-generation infrastructure) | Present-focused (what can we demo now with minimal effort) |
| **Technology stance** | Adopt new decentralized standards (DIDs, VCs, ToIP, digital wallets) | Use what's already on publisher sites; minimize changes |
| **Scale of change** | "Complete departure" from current architecture | Reduce scope to bare essentials |
| **Publisher concerns** | Not addressed directly | Central concern — brittle stacks, high risk of breakage |
| **Funding model** | VTN ecosystem with FPC partnerships | Consider advertiser funding; keep costs minimal |
| **AI relevance** | Central — AI agents drive need for decentralization | Not discussed |
| **Alignment with ITEGA mission** | Strong — VTN governance model maps to ITEGA's governing-not-operating role | Implicit — just get something working |
| **Risk** | High transition cost; immature ecosystem; multi-year timeline | Scope too small to prove the full vision |

---

## Where They Agree

Despite their different perspectives, Drummond and Don converge on several points:

1. **The full specification as written is too large for an initial deployment.** Drummond implies it by recommending a different technology foundation entirely; Don says it explicitly.
2. **ITEGA's governance model is sound.** Neither questions the four-party model or the governing-not-operating principle. Drummond explicitly says ITEGA's vision of an international news network is achievable.
3. **The vision is worth pursuing.** Both see value in what ITEGA is trying to accomplish — they disagree on how to get there, not whether to try.
4. **Interoperability standards matter.** Both emphasize open standards over proprietary solutions.

## Where They Diverge

1. **Build now vs. wait for new infrastructure.** Don says ship something minimal today; Drummond says the right infrastructure is emerging now and ITEGA should adopt it.
2. **OIDC as foundation.** Drummond views OIDC as legacy technology being superseded; Don implicitly accepts it as pragmatic.
3. **Scope of ambition for Phase 1.** Don wants to minimize; Drummond wants to maximize by joining a larger movement.
4. **Role of AI.** Drummond sees AI agents as the primary driver of architectural change; Don doesn't address AI.

---

## Recommended Path: Ship OIDC Pilot Now, Design for VTN Evolution

### The Dual-Track Strategy

Both reviewers are right — and their advice is complementary, not contradictory:

**Track 1: Ship the Missouri Pilot (Months 1-6)**
Follow Don's advice. Simplify the current OIDC-based prototype to the minimum demo-able version. Get real publishers and real users through the cross-publisher authentication flow. Prove the four-party model works with actual Missouri newspapers.

**Track 2: Plan the VTN Evolution (Months 3-12)**
Follow Drummond's advice. Engage with the First Person Cooperative about a media-industry VTN. Ensure the pilot architecture makes "bridge" design decisions that keep migration feasible. Document the evolution path.

### Why This Works

The OIDC pilot and the VTN vision are not in conflict because:

1. **The four-party model is protocol-agnostic.** The roles (End User, Home Base, Publisher, ALS) map cleanly onto ToIP's Verifiable Trust Network concept regardless of whether authentication uses OIDC or DID-based credentials.

2. **The current architecture already incorporates decentralized principles:**
   - **Pairwise Pseudonymous Identifiers (PPID)** — each user has a different opaque ID at each publisher, exactly the privacy model that VCs enforce
   - **No central identity database** — the network is distributed like DNS, consistent with decentralized identity
   - **W3C Verifiable Credentials already in the protocol stack** — the tech spec includes VC Data Model 2.0 for rich identity claims
   - **PII never leaves the home base** — data minimization is built in, not bolted on
   - **No cookies** — token-based authentication via HTTP headers is closer to the wallet/credential model than cookie-based SSO

3. **A working OIDC pilot proves the business model.** The technical plumbing can evolve; the hard part is getting publishers to participate, users to sign up, and the settlement model to work. Those are business problems, not protocol problems.

4. **ITEGA's governing-not-operating role maps directly to ToIP governance.** Drummond explicitly noted this. A pilot that validates the governance model is valuable regardless of the underlying authentication protocol.

---

## Bridge Design Decisions

These specific architectural choices in the current prototype keep the VTN migration path open:

| Current Design | Why It Bridges to VTN |
|---------------|----------------------|
| **PPID (pairwise pseudonymous IDs)** | Maps directly to DID-based selective disclosure. Users already get different IDs per publisher. |
| **W3C Verifiable Credentials in protocol stack** | VCs are the core credential format in ToIP/VTN. Already specified for rich identity claims. |
| **JWT tokens with RS256 signing** | JWTs are the serialization format for VCs (JWT-VC). Same token format, different issuance model. |
| **Home Base as sole identity authority** | Maps to the "digital wallet" concept — the user's home base becomes their credential issuer/wallet provider. |
| **ALS as neutral validator** | Maps to ToIP "verifier" role. The ALS validates credentials without knowing the user's identity. |
| **NetworkGroupId bitmask** | Can be encoded as a VC claim. The access-tier model is independent of the credential format. |
| **No cookies / header-based auth** | Consistent with wallet-based credential presentation. No browser dependency. |
| **WebFinger for discovery** | DID resolution serves the same purpose. Discovery layer is swappable. |
| **JSON-LD content tagging (RSL)** | Aligns with Content Authenticity Initiative (C2PA) metadata. Drummond specifically mentioned CAI as a VTN partner. |

---

## How the Four-Party Model Maps to ToIP/VTN

```
ITEGA Model                          ToIP/VTN Model
─────────────                        ──────────────
ITEGA (Governing Authority)    →     VTN Governance Authority
Home Base (IdSP)               →     Credential Issuer / Digital Wallet Provider
Publisher (Content Provider)   →     Verifier / Relying Party
ALS (Auth/Logging/Settlement)  →     Trust Registry + Verification Service
End User                       →     Holder (of Verifiable Credentials)
```

The mapping is nearly one-to-one. The key difference is that in the VTN model, credentials are presented directly from the user's wallet to the publisher (or via the ALS as a proxy verifier), rather than through OIDC redirects via the home base. This eliminates the redirect chain and enables AI agent authentication natively.

---

## Phase 2+ Migration Path

### From OIDC to DID-Based Authentication

| Phase | Authentication Model | What Changes |
|-------|---------------------|-------------|
| **Phase 1 (Current pilot)** | OIDC Authorization Code Flow via ALS | Nothing — ship as designed |
| **Phase 1.5 (Bridge)** | OIDC + optional VC presentation | Home bases can issue VCs alongside OIDC tokens. Publishers accept either. |
| **Phase 2 (Hybrid)** | DID-based auth preferred, OIDC fallback | Users with digital wallets use VC presentation. Legacy users fall back to OIDC. ALS accepts both. |
| **Phase 3 (Full VTN)** | DID/VC native | All authentication via verifiable credential presentation. OIDC deprecated. Home bases operate as credential issuers. |

### Concrete Next Steps for VTN Track

1. **Engage Drummond Reed and the First Person Cooperative** — explore whether a news-industry VTN is feasible within the FPC framework
2. **Connect with the Content Authenticity Initiative** — Drummond mentioned Adobe/CAI as a planned VTN partner; RSL and C2PA are complementary
3. **Map Newshare token claims to VC format** — define how `networkUserId`, `networkGroupId`, `pubMbrId` would be expressed as VC claims
4. **Evaluate ToIP trust registry** — determine whether the ALS could serve as (or integrate with) a ToIP trust registry
5. **Monitor First Person Project standards development** — particularly around VTN governance frameworks and trust agent specifications

---

## References

- **First Person Project** — [firstperson.global](https://firstperson.global) — White paper on decentralized digital identity and trust architecture
- **Trust Over IP Foundation** — [trustoverip.org](https://trustoverip.org) — Governance and technology framework for decentralized trust
- **W3C Decentralized Identifiers (DIDs)** — [w3.org/TR/did-core](https://www.w3.org/TR/did-core/) — W3C Recommendation for decentralized identifiers
- **W3C Verifiable Credentials** — [w3.org/TR/vc-data-model-2.0](https://www.w3.org/TR/vc-data-model-2.0/) — Data model for verifiable credentials (already in Newshare protocol stack)
- **Content Authenticity Initiative (C2PA)** — [c2pa.org](https://c2pa.org) — Content provenance and authenticity standards, led by Adobe
- **Agentic AI Foundation** — [linuxfoundation.org](https://www.linuxfoundation.org/) — Linux Foundation project for AI agent interoperability (A2A, MCP, AGNTCY)
- **Really Simple Licensing (RSL)** — [rslstandard.org](https://rslstandard.org) — Content rights tagging standard (already in Newshare protocol stack)

---

*This synthesis was prepared for ITEGA based on peer review feedback from Drummond Reed (received February 27, 2026) and Don Marti (received March 2, 2026).*
