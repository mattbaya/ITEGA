# Server Plan 03: ALS — Logging Service

*Spec reference: Sections 4.1, 4.2, 5.2*

## Purpose

The Logging Service records every value-exchange event on the Newshare Network — every article read, ad viewed, subscription credit, or reward event. It is the backbone of the settlement system: without accurate logs, no one gets paid. It operates on the principle of a privacy-preserving, append-only ledger.

**The ALS Logging Service never has access to personally identifiable information.** It receives only opaque `networkUserId` values and cannot correlate them to real people.

## Core Responsibilities

- Log every value-exchange event in the Extended Common Log Format
- Provide the authoritative data source for settlement calculations
- Deliver aggregated usage reports to:
  - **Home bases:** full clickstream by their users (for billing and analysis)
  - **Publishers:** aggregated totals sorted by home-base ID only (not by individual user)
- Maintain append-only, tamper-evident event log
- **Never** provide data to third parties
- **Never** enable cross-site user correlation by publishers

## Log Record Format (from spec Section 4.2)

Each value-exchange event contains the following fields, derived from the original Clickshare Extended Common Log Format:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 event timestamp |
| `networkUserId` | Opaque pairwise pseudonymous user ID |
| `homeBaseId` | Network ID of user's home base |
| `pubMbrId` | Network ID of content-serving publisher |
| `resourceId` | URL or DOI of the resource accessed |
| `pageClass` | Numeric value class (wholesale royalty amount) |
| `serviceClass` | User's NetworkGroupId at time of event |
| `markupRatio` | Retail markup ratio applied by home base |
| `eventType` | `content_access` \| `ad_view` \| `subscription_credit` \| `reward` |
| `sessionId` | ALS-assigned session identifier (not linkable to PII) |

## Data Access Rules (from spec Section 4.1)

| Recipient | What They Receive |
|-----------|-------------------|
| **Home Base** | Full clickstream by their users (for billing and analysis) |
| **Publisher** | Aggregated totals sorted only by home-base ID — **NOT by individual user** |
| **Third Parties** | **NOTHING.** Clickstream data is never sold or provided. |
| **Publishers attempting cross-correlation** | Prohibited by ITEGA membership rules. Subject to sanction. |

## Technology Stack

| Component | Technology | Rationale (from spec Section 5.2) |
|-----------|------------|-----------------------------------|
| **Database** | **TimescaleDB** (PostgreSQL extension for time-series) or **ClickHouse** | High-volume event logging optimized for time-series queries. TimescaleDB preferred because it runs on the same PostgreSQL instance as other components. |
| **Log Writer** | Lightweight async daemon (Python or Node.js) | Analogous to the original Clickshare `cs-logd`. Accepts events and writes to TimescaleDB asynchronously to avoid blocking publisher requests. |
| **Message Queue** | Redis Streams or simple file buffer | Buffer between real-time events and database writes |
| **Reporting** | SQL queries against TimescaleDB | Aggregation for settlement and usage reports |
| **Container** | Docker | Deployment isolation |

## Implementation Steps

### Phase 1: Event Logging Infrastructure (Weeks 1-3)
1. Set up TimescaleDB extension on PostgreSQL instance
2. Create hypertable for event logs (partitioned by timestamp)
3. Build async log writer daemon: accepts events via HTTP/message queue
4. Implement the Extended Common Log Format record structure
5. Set up append-only constraints (no UPDATE or DELETE on log table)
6. Implement event validation: reject records with missing required fields

### Phase 2: Reporting Engine (Weeks 3-5)
7. Build home-base usage report: full clickstream per user, grouped by home base
8. Build publisher usage report: aggregated totals by home-base ID only (no individual users)
9. Implement report scheduling (daily summary, weekly for settlement)
10. Build report delivery API (home bases and publishers pull their reports)
11. Add data retention policy: configurable retention period per ITEGA governance

### Phase 3: Privacy Verification & Pilot (Weeks 5-7)
12. **Audit all stored data:** verify zero PII in log records
13. Verify publisher reports contain no individual user data
14. Verify cross-site correlation is impossible from log data alone
15. Load test: simulate expected pilot event volume (50+ users, 3-5 publishers)
16. Deploy on pilot VM alongside PostgreSQL instance

## Infrastructure Requirements (Pilot)

- **Compute:** Shared with main PostgreSQL instance. The async daemon is lightweight.
- **Storage:** 10-20GB for pilot (event logs grow linearly with usage; TimescaleDB compresses well)
- **Network:** Internal only — not directly accessible from internet. Events arrive from ALS Auth Service.
- **Performance:** Write throughput: 100+ events/second (well beyond pilot needs). Query: sub-second for settlement aggregation.

## Security Considerations

- **Append-only:** Log records are immutable once written. No UPDATE or DELETE operations.
- **No PII:** Contains only opaque identifiers. Even if the database is compromised, no personal data is exposed.
- **Access control:** Only the ALS Auth Service can write events. Only settlement and reporting processes can read.
- **Tamper evidence:** Consider cryptographic hash chain (each record includes hash of previous) for audit integrity. Not strictly required for pilot but valuable for trust.
- **Encryption at rest:** AES-256 on the PostgreSQL tablespace.
- **Retention:** Configurable by ITEGA governance. Minimum required for settlement dispute resolution.

## Interfaces

- **ALS Auth Service** writes events after every validated user-publisher interaction
- **ALS Settlement Service** reads aggregated events for settlement calculations
- **Home Bases** receive usage reports for their users (via reporting API)
- **Publishers** receive aggregated reports (via reporting API)
- **ITEGA Governance** sets retention policies and auditing requirements
