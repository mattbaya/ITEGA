# Server Plan 02: ALS — Authentication Service

*Spec reference: Sections 2.1, 2.2, 4.1, 5.2*

## Purpose

The Authentication Service is one of three ALS (Authentication, Logging, Settlement) components. It is the neutral, ITEGA-licensed infrastructure that validates authentication tokens in real time when a user visits a publisher. It operates analogously to DNS — logically centralized but physically distributable.

**Critical constraint: The ALS never has access to names, email addresses, or financial information.** It knows users only by their opaque `networkUserId`.

## Core Responsibilities

- Validate authentication tokens (JWT) in real time when publishers query
- Verify token signatures against home base public keys
- Check token expiry and session validity
- Issue `sessionToken` (signed JWT with configurable duration)
- Route authentication flows between home bases and publishers
- Maintain registry of certified home base public keys
- **No PII access ever** — only sees opaque networkUserId and networkGroupId

## How It Works in the Authentication Flow

```
Step 3: User selects "Network Login" at Publisher B
        → Publisher B redirects to ALS Auth Service
Step 4: ALS checks for home-site cookie. If found, redirects to Home Base.
        If not, user selects home base from list.
Step 6: Home Base sends networkUserId + networkGroupId back through ALS
        → ALS validates token, issues sessionToken
        → Redirects to Publisher B with validated credentials
```

Once authenticated, Publisher B can cache the session. On session expiry, the ALS transparently re-authenticates via the home base.

## Technology Stack

| Component | Technology | Rationale (from spec Section 5.2) |
|-----------|------------|-----------------------------------|
| **Runtime** | Custom lightweight service built on chosen OIDC provider's token validation endpoint | For pilot, runs as **sidecar to Keycloak/Authentik**. At scale, mirrors original distributed CALS architecture. |
| **Language** | Python (FastAPI) or Node.js (Fastify) | Lightweight, fast token validation |
| **JWT Library** | `python-jose` / `jsonwebtoken` (Node) | RS256 signature verification |
| **Key Store** | In-memory cache of home base JWKS (refreshed periodically) | Fast public key lookup for token verification |
| **Cache** | Redis 7 | Session token cache, home-site cookie equivalent |
| **Container** | Docker | Deployment isolation |

## Key Data Handled

The ALS Auth Service handles ONLY these fields — no PII:

| Field | Purpose |
|-------|---------|
| `networkUserId` | Opaque PPID — cannot be linked to real identity |
| `homeBaseId` | Which home base issued the token |
| `networkGroupId` | Subscription tier bitmask |
| `sessionToken` | Signed JWT for session duration |
| `pubMbrId` | Which publisher the user is visiting |

## Implementation Steps

### Phase 1: Token Validation (Weeks 1-2)
1. Build JWT validation endpoint: verify signature, expiry, issuer
2. Implement JWKS (JSON Web Key Set) fetching from certified home bases
3. Cache home base public keys with configurable refresh interval
4. Build session token issuance: sign new sessionToken after validating home base token
5. Implement token replay protection (nonce validation)

### Phase 2: Authentication Routing (Weeks 2-4)
6. Build home-site discovery flow: check for home-site indicator, present selection if none
7. Implement redirect flow: Publisher → ALS → Home Base → ALS → Publisher
8. Handle the OIDC Authorization Code exchange on behalf of the network
9. Build error handling for expired sessions (transparent re-authentication)
10. Implement configurable session duration per network policy

### Phase 3: Pilot Integration (Weeks 4-6)
11. **For pilot: run as sidecar to Keycloak/Authentik** (same VM, same instance)
12. Register pilot home base(s) public keys
13. Test full authentication loop with WordPress plugin at publisher sites
14. Verify no PII leakage: audit all data the ALS service handles
15. Performance testing: token validation latency < 50ms p95

## Infrastructure Requirements (Pilot)

- **Compute:** Runs on same VM as Keycloak (sidecar). Minimal additional resources.
- **Storage:** Negligible (stateless; session tokens in Redis)
- **Network:** Publicly accessible HTTPS endpoint for publishers to call
- **Latency:** < 50ms p95 for token validation (critical path for user experience)
- **Availability:** 99.9% (authentication is on the critical path)

## Security Considerations

- NEVER stores or logs PII — only opaque identifiers
- All token validation uses asymmetric cryptography (RS256) — ALS never holds private keys
- Home-site discovery must not leak which home base a user belongs to (except to the user)
- Token replay protection via nonce/jti claims
- Rate limiting to prevent brute-force token probing
- All inter-service communication over TLS 1.3
- Audit log of all token validation events (for security analysis, not for billing)

## Interfaces

- **Home Bases** register their JWKS (public keys) with this service
- **Publishers** call this service to validate user tokens
- **ALS Logging Service** receives validated event data to record
- **Network Discovery** provides the list of certified home bases and their JWKS URIs
- **ITEGA Governance** sets session duration policies and certification rules
