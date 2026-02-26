# Server Plan 06: Network Discovery Service

*Spec reference: Sections 3.1, 5.2, 6.1*

## Purpose

The Network Discovery Service is the directory of the Newshare Network — analogous to the original Clickshare Interchange Service (CIS) master ID database, or DNS for the internet. It is an OIDC Discovery endpoint hosted at a well-known ITEGA URL that lists all certified home bases and publishers on the network. When a user clicks "Network Login" and the system needs to find their home base, this is where it looks.

## Core Responsibilities

- Host OIDC Discovery endpoint at well-known ITEGA URL (e.g., `https://network.itega.org/.well-known/openid-configuration`)
- Maintain registry of all certified home bases (IdSPs) with their OIDC endpoints and public keys
- Maintain registry of all certified publishers (Content Providers)
- Enable home-site discovery via WebFinger (RFC 7033)
- Publish network-wide OIDC configuration
- Serve as the trust anchor: only ITEGA-certified participants appear in the directory

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Runtime** | Static JSON files served via Nginx, or lightweight API (FastAPI/Express) | Minimal infrastructure; this is essentially a directory service |
| **Data Store** | PostgreSQL or flat JSON files (pilot) | Small dataset — list of certified members |
| **WebFinger** | RFC 7033 implementation | Standard protocol for home-site discovery |
| **Hosting** | Same cloud VM as other ALS components (pilot) | No separate infrastructure needed |

## Discovery Flow

```
1. User clicks "Network Login" at Publisher B
2. Publisher B's plugin redirects to ALS Auth Service
3. ALS Auth checks for home-site indicator:
   a. If found → redirect directly to that home base
   b. If not found → query Network Discovery for list of home bases
4. User selects their home base from the list
5. ALS redirects to selected home base for authentication
6. Home base is found via its registered OIDC Discovery endpoint
```

## Data Model

```json
{
  "network": "Newshare Network",
  "version": "1.0",
  "governed_by": "ITEGA",
  "home_bases": [
    {
      "id": "HB001",
      "name": "Columbia Missourian",
      "oidc_issuer": "https://auth.columbiamissourian.com",
      "jwks_uri": "https://auth.columbiamissourian.com/.well-known/jwks.json",
      "certification_status": "active",
      "certification_tier": "idsp",
      "certified_date": "2026-06-01"
    }
  ],
  "publishers": [
    {
      "id": "PUB001",
      "name": "Joplin Globe",
      "domain": "www.joplinglobe.com",
      "certification_status": "active",
      "certification_tier": "content_publisher"
    }
  ]
}
```

## Implementation Steps

### Phase 1: Basic Discovery (Weeks 1-2)
1. Set up OIDC Discovery endpoint at well-known ITEGA URL
2. Implement WebFinger (RFC 7033) for home-site discovery
3. Create certified member registry (JSON or database)
4. Build admin interface for ITEGA to add/remove/suspend members

### Phase 2: Pilot Deployment (Weeks 2-3)
5. Register pilot home base and publishers in the directory
6. Test discovery flow: user arrives at publisher → finds home base
7. Implement home-site hint mechanism (so returning users don't re-select)
8. Deploy on pilot VM

## Infrastructure Requirements

- **Compute:** Negligible — serves mostly static data
- **Storage:** < 1GB
- **Network:** Publicly accessible HTTPS
- **Availability:** 99.9% — discovery is on the authentication critical path
- **Cache:** CDN-cacheable with short TTL (5-15 minutes)

## Interfaces

- **ALS Auth Service** queries this for home base OIDC endpoints and JWKS URIs
- **Publishers** (via plugin) use this for initial OIDC configuration
- **Home Bases** register their endpoints here upon ITEGA certification
- **ITEGA Governance** manages the registry (add, suspend, revoke certifications)
