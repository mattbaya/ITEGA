# Server Plan 04: ALS — Settlement Service

*Spec reference: Sections 4.3, 5.2, 3.4*

## Purpose

The Settlement Service is the financial clearing house of the Newshare Network. It runs as a **batch process** (not real-time) that reads the logging database, computes what each home base owes and what each publisher is owed, deducts ITEGA's transaction fee, and initiates ACH bank transfers. This is the component that makes the "commerce" in "information commerce" actually work.

**The settlement service does not require real-time operation.** It runs offline against the log database, separating performance-critical authentication from batch financial processing — exactly as in the original 1996 TVS architecture.

## Core Responsibilities

- Aggregate all log records for the settlement period
- Compute total charges owed by each home base to the network
- Compute total credits owed to each publisher
- Calculate and deduct ITEGA's transaction fee (small percentage of settled value)
- Generate ACH debit/credit files for processing through the U.S. banking ACH network
- Deliver itemized usage reports:
  - To home bases: full clickstream by their users
  - To publishers: aggregated totals by source home base
- Handle dispute resolution data

## The Wholesale-Retail Pricing Model (from spec Section 3.4)

This is how money flows through the network:

```
Publisher sets:     pageClass = $0.05 (wholesale price per article)
Home Base sets:     markupRatio = 1.4 (40% retail markup)
User sees:          $0.07 retail price before committing

Settlement:
  → Publisher receives $0.05 credit
  → Home Base is debited $0.05 (pays publisher at wholesale)
  → Home Base keeps $0.02 margin (retail - wholesale)
  → ITEGA receives small transaction fee (e.g., 1-2% of settled value)
```

Two users from different home bases may see different retail prices for the same article — just as the same product sells for different prices at different stores.

## Settlement Process (from spec Section 4.3)

The settlement runs on a configurable cycle (daily, weekly, or monthly; **weekly is recommended for the pilot**):

| Step | Action |
|------|--------|
| 1 | Aggregate all log records for the settlement period |
| 2 | Group by `homeBaseId` → compute total charges owed by each home base |
| 3 | Group by `pubMbrId` → compute total credits owed to each publisher |
| 4 | Compute ITEGA's transaction fee (small % of settled value — the network's revenue model) |
| 5 | Generate ACH debit/credit files for banking ACH network |
| 6 | Deliver itemized usage reports to home bases (full clickstream) |
| 7 | Deliver aggregated reports to publishers (totals by source home base) |

## Technology Stack

| Component | Technology | Rationale (from spec Section 5.2) |
|-----------|------------|-----------------------------------|
| **Runtime** | **Python 3.12** or **Node.js 22** | Batch processing script. Python preferred for data aggregation libraries. |
| **Payment Processing** | **Stripe Connect** API | Marketplace payment splitting mirrors home-base/publisher model. Handles KYC, ACH origination, reporting. Modern replacement for 1996 Bank of Boston ACH interface. |
| **Alternative Payment** | **Stripe Treasury**, **Dwolla**, or direct bank ACH integration | Other viable options per spec |
| **Database** | Reads from TimescaleDB (logging service) | No separate database — settlement queries the log |
| **Scheduler** | **Cron** (pilot) / **Celery** or **Temporal** (production) | Weekly batch execution |
| **Report Generation** | Python (pandas/CSV) or custom | Settlement reports in standard format |
| **Container** | Docker | Deployment isolation |

## Settlement Data Model

```sql
-- Settlement runs (one per batch)
settlement_runs:
  id, period_start, period_end, status, total_settled, itega_fee, created_at

-- Per-home-base debits
home_base_debits:
  settlement_id, home_base_id, total_events, total_wholesale, total_retail, amount_owed

-- Per-publisher credits
publisher_credits:
  settlement_id, pub_mbr_id, total_events, total_wholesale, amount_earned

-- ACH transactions
ach_transactions:
  settlement_id, party_id, party_type, amount, direction, stripe_transfer_id, status

-- Disputes
disputes:
  id, settlement_id, filed_by, description, status, resolution
```

## Implementation Steps

### Phase 1: Settlement Engine (Weeks 1-3)
1. Build SQL aggregation queries against TimescaleDB log data:
   - Total by homeBaseId (debits)
   - Total by pubMbrId (credits)
   - Apply markupRatio calculations
2. Implement ITEGA transaction fee calculation (configurable percentage)
3. Build settlement report generation:
   - Home base report: itemized clickstream by user
   - Publisher report: aggregated totals by home base (no individual users)
4. Implement settlement run lifecycle: pending → processing → completed → distributed
5. Build dispute data export (for manual resolution)

### Phase 2: Payment Integration (Weeks 3-5)
6. Set up Stripe Connect platform account for Newshare Network
7. Implement publisher onboarding to Stripe Connect (KYC, bank account linking)
8. Implement home base onboarding to Stripe Connect (as "customers" or "connected accounts")
9. Build ACH debit generation: charge home bases for their users' content consumption
10. Build ACH credit generation: pay publishers for content served
11. **For pilot: simulate ACH** — generate the files and reports but use test mode for actual transfers

### Phase 3: Reporting & Pilot (Weeks 5-7)
12. Build report delivery: API endpoint or email delivery of settlement reports
13. Implement reconciliation: verify debits = credits + ITEGA fee
14. Set up weekly cron job for pilot settlement cycle
15. Run end-to-end test: simulated events → settlement → simulated ACH files
16. Deploy on pilot VM

## Infrastructure Requirements (Pilot)

- **Compute:** Minimal — batch job runs once per week. Uses main PostgreSQL instance.
- **Storage:** Settlement records are small. 1-2GB for pilot.
- **Network:** Outbound HTTPS to Stripe API. No inbound traffic needed.
- **Scheduling:** Simple cron job (pilot). No always-on process required.
- **Cost:** Stripe Connect fees (2.9% + $0.30 per card; ACH is lower). Minimal for pilot volumes.

## Security Considerations

- Settlement engine has **read-only** access to log database
- Financial calculations must be deterministic and auditable
- All ACH files encrypted in transit and at rest
- Stripe Connect handles PCI compliance for payment processing
- Settlement reports to publishers contain NO individual user data
- Dispute records maintained with full audit trail
- ITEGA fee percentage governed by board, not by operator
- Reconciliation check: sum(debits) must equal sum(credits) + sum(fees) for every run

## Pilot vs. Production Notes

| Aspect | Pilot | Production |
|--------|-------|------------|
| ACH Processing | **Simulated** (generate files, don't process) | Real ACH via Stripe Connect |
| Settlement Cycle | Weekly | Configurable (daily/weekly/monthly) |
| Scheduler | Cron | Temporal.io or Celery |
| Scale | ~50 users, 3-5 publishers | Thousands of users, hundreds of publishers |
| Dispute Resolution | Manual (email) | Structured workflow |

## Interfaces

- **ALS Logging Service** provides the event data (read-only access to TimescaleDB)
- **Home Bases** receive debit notifications and itemized usage reports
- **Publishers** receive credit notifications and aggregated usage reports
- **Stripe Connect** processes actual ACH transfers (production) or test transfers (pilot)
- **ITEGA Governance** sets transaction fee percentage and settlement policies
