# Server Plan 01: Home Base (Identity Service Provider / IdSP)

*Spec reference: Sections 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 5.2*

## Purpose

The Home Base is where a reader creates their one account on the Newshare Network. It is the **only party that knows the user's real identity**. It authenticates users, manages their profiles and privacy preferences, generates pairwise pseudonymous identifiers (PPIDs) for each publisher the user visits, and handles retail billing/markup.

In the pilot, one Keycloak/Authentik instance serves as both the demo Home Base **and** the ALS authentication service. In production, any certified entity (publisher, ISP, library) can operate a Home Base.

## Core Responsibilities

- User registration and account management (the ONLY place users sign up)
- OIDC Provider: issue ID Tokens with custom claims (networkUserId, networkGroupId)
- Generate and manage **pairwise pseudonymous identifiers** (PPID) per user+publisher pair
- Store user profile attributes (PII separated from anonymizable demographics)
- Manage user privacy preferences (privacyLevel, adPreference, doNotTrack)
- Map internal subscription records to NetworkGroupId bitmask
- Apply retail **markupRatio** to publisher wholesale prices
- Bill users for content accessed across the network
- Pay publishers for content consumed by home-base users (via ALS settlement)

## Key Design Constraints (from spec)

- **No cookies for authentication.** Auth state passed via HTTP headers / tokens only.
- **Pairwise IDs:** Each user gets a different `networkUserId` for each publisher they visit. Format: `[HomeBaseID]-[OpaqueToken]`. This makes cross-site correlation impossible without home base cooperation.
- **The home base can unlink a user** from any or all publishers at any time, effectively making them "disappear" from that publisher's records.
- **PII never leaves the home base.** The ALS only receives the opaque `networkUserId` and `networkGroupId`.

## Protocol Requirements

| Function | Protocol | Spec Reference |
|----------|----------|----------------|
| SSO Provider | OpenID Connect 1.0 (Authorization Code Flow) | Section 3.1 |
| Token format | JWT (RFC 7519) | Section 3.1 |
| Home-site discovery | OIDC Discovery (`.well-known/openid-configuration`) + WebFinger (RFC 7033) | Section 3.1 |
| Pairwise user IDs | OIDC PPID per OIDC Core spec Section 8 | Section 2.3 |
| Rich identity claims | W3C Verifiable Credentials (VC Data Model 2.0) | Section 3.1 |
| Token encryption | JWE (RFC 7516) for sensitive claims | Section 3.1 |
| NetworkGroupId | Custom claim in OIDC ID Token (bitmask) | Section 2.4 |
| User attributes | Schema.org/Person + Internet2 eduPerson | Section 3.2 |
| Transport | TLS 1.3 mandatory | Section 3.1 |

## Technology Stack

| Component | Technology | Rationale (from spec Section 5.2) |
|-----------|------------|-----------------------------------|
| **OIDC Provider** | **Keycloak** (Java, Apache 2.0) or **Authentik** (Python/Go) | Both support OIDC, PPID, custom claims, federation. Keycloak has stronger enterprise adoption; Authentik has modern admin UX. Either can serve as home base IdSP for the pilot. |
| **User Profile Store** | **PostgreSQL 16** with Clickshare Customer Profile Server schema | Derived from the 2017 Clickshare schema (spec Section 3.2). **Apache Unomi** (open-source W3C Context API) is a candidate profile management layer. |
| **Cache** | **Redis 7** | Session tokens, PPID lookup cache |
| **Reverse Proxy** | **Nginx** or **Caddy** | TLS termination, header manipulation for token passing |
| **Container** | **Docker** | Deployment isolation |

## User Attribute Schema (from spec Section 3.2)

### Network-Level Attributes (accompany all authenticated requests)

| Attribute | Description |
|-----------|-------------|
| `networkUserId` | Globally unique PPID. Format: `[HomeBaseID]-[OpaqueToken]` |
| `homeBaseId` | Network ID of user's home base (analogous to credit card issuer ID) |
| `networkGroupId` | Bitmask encoding subscription tier and access rights |
| `sessionToken` | Signed JWT issued by ALS. Configurable session duration |
| `pubMbrId` | Network ID of content-serving publisher |

### Preference-Level Attributes (user-controlled, govern all requests)

| Attribute | Type |
|-----------|------|
| `privacyLevel` | Enum: open, limited, private |
| `adPreference` | Enum: full ads, links only, no ads |
| `doNotTrack` | Boolean |
| `parentalControl` | Boolean |
| `ageRange` | Enum: <13, 13-17, 18-24, 25-34, 35-44, 45-54, 55-64, 65+ |

### Optional Identity Attributes (shared only with explicit user permission)

| Attribute | Type |
|-----------|------|
| `nickname` | String (display name, not necessarily real) |
| `email` | String, 255 chars. PII — explicit consent only |
| `gender` | Enum: preferNotToSay, male, female, genderQueer, other |
| `postalCode` | String, 15 chars |
| `country` | ISO 3166-1 alpha-2 |
| `language` | BCP 47 language tag |
| `income` | Enum ranges: <20K through 200K+ |
| `education` | Enum: primary, secondary, postSecondary |
| `employment` | Enum: notEmployed, looking, partTime, fullTime, retired, disabled |
| `interests` | Array of freeform keywords |

## PPID Generation Logic

```
Input:  internal_user_id (e.g., 12345)
        publisher_network_id (e.g., "NNN" for Publisher B)

Output: networkUserId = "[HomeBaseID]-[hash(internal_user_id + publisher_network_id + secret)]"

Rule:   Same user visiting Publisher B always gets same networkUserId
        Same user visiting Publisher C gets a COMPLETELY DIFFERENT networkUserId
        Publishers B and C cannot correlate these IDs without home base cooperation
```

This implements what the W3C OIDC spec calls a Pairwise Pseudonymous Identifier (PPID), now a recognized standard.

## Implementation Steps

### Phase 1: OIDC Provider Setup (Weeks 1-3)
1. Deploy Keycloak (or Authentik) on cloud VM with PostgreSQL backend
2. Configure ITEGA/Newshare realm with custom branding
3. **Implement PPID support:** Configure pairwise subject identifiers in Keycloak
4. Add custom JWT claims: `networkUserId`, `networkGroupId`, `homeBaseId`, `pubMbrId`
5. Implement OIDC Discovery endpoint (`.well-known/openid-configuration`)
6. Set up WebFinger (RFC 7033) for home-site discovery
7. Configure CORS and redirect URIs for pilot publisher domains

### Phase 2: User Profile Store (Weeks 3-5)
8. Implement user profile schema per spec Section 3.2 (PII / non-PII separation)
9. Build privacy preference management (privacyLevel, adPreference, doNotTrack)
10. Implement age range enum for COPPA compliance (under-13 flag without storing birthdate)
11. Build PPID mapping table: `internal_user_id → publisher_id → networkUserId`
12. Implement user attribute sharing API (consent-gated, respects privacyLevel)
13. Build user unlinking: ability to revoke any/all PPIDs (user "disappears" from publisher)

### Phase 3: Billing & Pricing (Weeks 5-7)
14. Implement NetworkGroupId bitmask mapping from internal subscription records
15. Build wholesale-retail pricing: receive publisher's `pageClass`, apply home base `markupRatio`
16. Implement user billing aggregation (consolidate charges from all publishers visited)
17. Build real-time price display: show retail price before user commits to purchase
18. Integrate with ALS settlement reports for debit reconciliation

### Phase 4: Missouri Pilot Integration (Weeks 7-10)
19. Register home base with ITEGA Network Discovery endpoint
20. Configure OIDC client registrations for each pilot publisher (3-5 Missouri newspapers)
21. Onboard pilot users with simplified registration flow
22. Test cross-publisher authentication: user at Home Base → Publisher B → recognized
23. Verify PPID isolation: confirm publishers see different IDs for same user
24. Load testing with pilot traffic expectations

## Infrastructure Requirements (Pilot)

- **Compute:** 2 vCPU, 4GB RAM (Keycloak) on single cloud VM (shared with ALS)
- **Storage:** 50GB SSD for PostgreSQL (user profiles + PPID mappings)
- **Network:** HTTPS only, TLS 1.3. Publicly accessible for OIDC endpoints.
- **Cost:** Included in $300-$500/month pilot VM budget
- **Backup:** Daily PostgreSQL snapshots

## Security Considerations

- All user PII encrypted at rest (AES-256)
- Passwords hashed with bcrypt/argon2 (Keycloak default)
- PPID secret key stored securely; rotation policy
- JWT signing with RS256 (asymmetric keys for cross-service verification)
- No cookies: all auth state via HTTP headers and signed tokens
- Rate limiting on login endpoints
- User unlinking must be instantaneous and irreversible at publisher
- MFA support (TOTP) for user accounts

## Interfaces

- **Publishers** redirect users here for authentication (OIDC Authorization Code Flow)
- **ALS Auth Service** validates tokens issued by this home base
- **ALS Settlement Service** sends settlement reports (debits for this home base's users)
- **Network Discovery** lists this home base as a certified IdSP
- **Users** register, manage profile, set privacy preferences, view bills here
