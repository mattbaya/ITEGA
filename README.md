# The Newshare Network

**A Federated Identity, Single Sign-On, and Fair Payment Network for Independent Journalism**

Governed by the [Information Trust Exchange Governing Association (ITEGA)](https://www.itega.org), a 501(c)(3) nonprofit.

---

## Table of Contents

- [What Is This?](#what-is-this)
- [The Problem It Solves](#the-problem-it-solves)
- [How It Works — The Visa Analogy](#how-it-works--the-visa-analogy)
- [A Complete Example: Susan Reads the News](#a-complete-example-susan-reads-the-news)
- [The Four-Party Model](#the-four-party-model)
- [How It's Different from "Sign in with Google"](#how-its-different-from-sign-in-with-google)
- [The Privacy Architecture: Pairwise Pseudonymous Identifiers](#the-privacy-architecture-pairwise-pseudonymous-identifiers)
- [The Wholesale-Retail Pricing Model](#the-wholesale-retail-pricing-model)
- [The NetworkGroupId: How Subscription Tiers Work](#the-networkgroupid-how-subscription-tiers-work)
- [Authentication Flow: Step by Step](#authentication-flow-step-by-step)
- [What Gets Logged (and What Doesn't)](#what-gets-logged-and-what-doesnt)
- [Settlement: How Publishers Get Paid](#settlement-how-publishers-get-paid)
- [Technical Architecture](#technical-architecture)
- [Protocol Stack](#protocol-stack)
- [Technology Stack](#technology-stack)
- [Missouri Pilot: Proof of Concept](#missouri-pilot-proof-of-concept)
- [Project Structure](#project-structure)
- [Competitive Landscape](#competitive-landscape)
- [History and Lineage](#history-and-lineage)
- [Key People](#key-people)
- [Source Documents](#source-documents)
- [Peer Review Feedback](#peer-review-feedback)
- [Evolution Path: From OIDC to Verifiable Trust Networks](#evolution-path-from-oidc-to-verifiable-trust-networks)
- [Bill Densmore's 7 Peer Review Questions](#bill-densmores-7-peer-review-questions)

---

## What Is This?

The Newshare Network is a proposed system that lets a reader **create one account at a local newspaper and be recognized — without re-registering — at any other participating newspaper** in the network. Transactions are logged by a neutral service, and publishers are paid fairly through periodic bank settlements. No platform intermediary takes a cut. No one builds a surveillance profile of what you read.

It is **not** a startup. It is **not** a platform. It is an open, nonprofit-governed infrastructure layer — like the internet's DNS, or like the banking system's ACH network — that independent publishers can use to share identity, access, and payment without surrendering control to Google, Meta, Apple, or any commercial gatekeeper.

The architecture was first built as a working prototype in 1996 by Clickshare Service Corp. and patented in 2008 (U.S. Patent No. 7,324,972 — now expired and in the public domain). The 2026 specification maps that proven design onto modern open standards: OpenID Connect, JSON Web Tokens, W3C Verifiable Credentials, and the Really Simple Licensing (RSL) standard for content rights.

---

## The Problem It Solves

Local news is in crisis. The number of local journalists in the United States has declined by more than 75% in the past two decades. The economic model that sustained independent journalism — local advertising and subscriptions — has collapsed, largely because Google and Meta have captured the majority of digital advertising revenue.

The **technical root cause** is something rarely named plainly: **independent publishers have no shared infrastructure for identity, access, or payment.** Every reader who wants to support multiple local news organizations must register separately at each one. Publishers cannot recognize a loyal reader arriving from a neighboring publication. No mechanism exists for a reader's home publisher to vouch for them at another publisher, or for content value to be settled fairly across a network without a platform intermediary.

The platforms that have stepped into this vacuum — "Sign in with Google," Facebook Connect — are not solutions. They are the problem: surveillance infrastructure that extracts reader data, captures advertiser revenue, and leaves publishers with less every year.

---

## How It Works — The Visa Analogy

The easiest way to understand the Newshare Network is the **Visa analogy**:

| Credit Card System | Newshare Network |
|-------------------|------------------|
| **Visa International** sets the rules, certifies banks, enforces standards | **ITEGA** sets the rules, certifies participants, enforces standards |
| **Your bank** (issuer) gives you a card and bills you | **Your home base** (a publisher/ISP/library) gives you an account and bills you |
| **A merchant** accepts Visa cards from any issuing bank | **A publisher** accepts readers from any certified home base |
| **The ACH network** settles transactions between banks | **The ALS** logs events and settles payments between home bases and publishers |
| Your bank knows who you are; the merchant just sees a card number | Your home base knows who you are; the publisher just sees an opaque ID |
| Visa doesn't own your bank or the merchant — it governs | ITEGA doesn't own your home base or the publisher — it governs |

And just like accepting Visa doesn't prevent a store from issuing its own loyalty card, joining the Newshare Network doesn't prevent a publisher from keeping its own subscriber system. The network is **additive, not a replacement**.

---

## A Complete Example: Susan Reads the News

Let's walk through a concrete scenario with real Missouri newspapers:

### Setup

- **Susan** lives in Columbia, Missouri. She subscribes to the **Columbia Missourian**, a daily newspaper run by the Missouri School of Journalism. The Missourian is her "home base" on the Newshare Network.
- The **Joplin Globe**, about 200 miles southwest, is also a member of the Newshare Network.
- Susan has never created an account at the Joplin Globe.

### What Happens

**Step 1: Susan finds an interesting article.**
Susan sees a link on social media to a Joplin Globe investigation about water quality in southwest Missouri. She clicks the link.

**Step 2: The Globe detects she's not a local subscriber.**
The Globe's website (running WordPress with the Newshare plugin) sees Susan has no local session. Instead of showing a generic paywall that says "Subscribe to the Joplin Globe for $9.99/month," it presents an additional option: **"Log in with your news network account."**

**Step 3: Susan clicks "Log in with your news network account."**
The Globe's plugin redirects Susan to the Newshare Network's authentication service (ALS). The ALS checks whether Susan has previously identified her home base. She has — the Columbia Missourian. The ALS redirects her browser to the Missourian's login page.

**Step 4: Susan logs in at the Missourian (her home base).**
Susan enters her Missourian username and password (or uses a passkey). This is the same login she uses to read the Missourian. She's on familiar ground.

**Step 5: The Missourian vouches for Susan — but doesn't reveal who she is.**
The Missourian's system does several things:
- Confirms Susan is a valid, paid digital subscriber (NetworkGroupId = `4104`: Digital Subscriber + Print Subscriber)
- Generates a **pairwise pseudonymous identifier** for Susan at the Globe. This is an opaque string like `HB001-a7f3bc92e41d`. It is **completely different** from the ID the Missourian would generate if Susan visited a third newspaper.
- Sends this ID and her subscription tier back through the ALS to the Globe.

**The Missourian never sends Susan's name, email address, or any personal information to the Globe or to the ALS.**

**Step 6: The Globe serves Susan the article.**
The Globe's WordPress plugin receives Susan's NetworkGroupId (`4104`). It maps this to its own access controls: paid subscribers get full access. Susan sees the complete investigation — no paywall, no registration, no friction.

The Globe knows only that a user identified as `HB001-a7f3bc92e41d`, a paid subscriber from the Columbia Missourian's home base, accessed the article. That's it.

**Step 7: The access event is logged.**
The ALS Logging Service records: timestamp, the opaque user ID, the Globe's publisher ID, the Missourian's home-base ID, the article URL, the wholesale price (`pageClass`), the subscription tier, and the event type (`content_access`). No personal information is recorded.

**Step 8: At the end of the week, settlement happens.**
The ALS Settlement Service runs a batch job:
- The Globe is owed $0.05 (the wholesale `pageClass` it set for the article).
- The Missourian is debited $0.05 for Susan's access.
- The Missourian charges Susan whatever retail price it has set — perhaps nothing extra (it's included in her subscription bundle), or perhaps a small additional charge.
- ITEGA receives a small transaction fee (say 1.5% of the $0.05 = $0.00075).
- ACH transfers move the money between bank accounts.

**Susan reads one article. She logs in once, at a place she trusts. No new account. No personal data shared. The publisher gets paid. Everyone knows only what they need to know.**

### What if Susan Visits a Third Newspaper?

If Susan later visits the **Springfield News-Leader**, the same flow repeats — but the Missourian generates a **completely different pseudonymous ID** for Susan at the News-Leader. The Globe sees `HB001-a7f3bc92e41d`. The News-Leader sees `HB001-5e8912dc7b3a`. These IDs cannot be correlated. The Globe and the News-Leader cannot determine that the same person visited both sites. This is by design.

### What if Susan Wants to "Disappear"?

If Susan ever wants to stop being recognized at the Globe, she can tell the Missourian (her home base) to **unlink her Globe ID**. The opaque identifier `HB001-a7f3bc92e41d` is immediately revoked. The Globe's records still contain the old ID, but it will never match any future request. Susan has effectively vanished from the Globe's system — without the Globe needing to do anything.

---

## The Four-Party Model

The Newshare Network has four distinct parties with defined roles:

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
│  HOME BASE        │    │  ALS (Auth / Logging  │    │  PUBLISHER        │
│  (IdSP)           │    │  / Settlement)        │    │  (Content         │
│                   │    │                      │    │   Provider)       │
│ • Authenticates   │    │ • Validates tokens   │    │ • Serves content  │
│   the user        │    │ • Logs every access  │    │ • Sets wholesale  │
│ • Only party that │    │   event              │    │   prices          │
│   knows user's    │    │ • Settles payments   │    │ • Accepts users   │
│   real identity   │    │   via ACH            │    │   from any home   │
│ • Generates       │    │ • Never sees PII     │    │   base            │
│   pseudonymous    │    │                      │    │ • Runs WordPress  │
│   IDs per         │    │                      │    │   + plugin         │
│   publisher       │    │                      │    │                   │
│ • Sets retail     │    │                      │    │                   │
│   markup          │    │                      │    │                   │
└──────────────────┘    └──────────────────────┘    └──────────────────┘
```

| Party | Who They Are | What They Know |
|-------|-------------|----------------|
| **End User** | A reader (e.g., Susan) | Their own identity, their home base, their reading history at their home base |
| **Home Base (IdSP)** | A publisher, ISP, library, or other trusted entity (e.g., the Columbia Missourian) | The user's real identity, profile, subscription tier. The home base is the **only** entity with this information. |
| **Publisher (Content Provider)** | A news organization on the network (e.g., the Joplin Globe) | Only that an opaque user ID from a certain home base, with a certain subscription tier, accessed a certain article. Nothing else. |
| **ALS** | A neutral, ITEGA-licensed infrastructure operator (e.g., Clickshare Service Corp.) | Only opaque user IDs, home base IDs, publisher IDs, and transaction amounts. **Zero personally identifiable information.** |
| **ITEGA** | The nonprofit governing authority | Network rules, certification records, membership agreements. ITEGA does not operate any services and has no access to user data. |

---

## How It's Different from "Sign in with Google"

| | Sign in with Google | Newshare Network |
|-|--------------------|--------------------|
| **Who owns the user's identity?** | Google | The user's chosen home base (a local publisher, ISP, or library) |
| **Does the platform track what you read?** | Yes. Google learns every site you log into. | No. The ALS sees only opaque IDs. Your home base sees your clickstream, but no one else does. |
| **Can sites correlate your activity?** | Yes. Google gives sites the same user ID across all of them. | No. Each publisher sees a **different** pseudonymous ID for the same user (PPID). |
| **Who profits?** | Google captures data and sells ads against it. | Publishers and home bases keep revenue. ITEGA takes a small governance fee. |
| **Can you "disappear" from a site?** | Not really. Deletion requests are at Google's discretion. | Yes. Your home base can instantly and irreversibly unlink your ID from any publisher. |
| **Who sets the price of content?** | Google/platform control ad marketplace pricing. | Publishers set wholesale prices. Home bases set retail markup. No platform intermediary. |
| **Does the service use cookies?** | Yes, extensively. | No. Auth state is passed via HTTP headers and signed tokens. A founding design principle since 1996. |
| **Is there a central identity database?** | Yes, at Google. | No. The network is distributed like DNS. Each home base manages its own users. |

---

## The Privacy Architecture: Pairwise Pseudonymous Identifiers

This is the single most important privacy feature of the Newshare Network.

When Susan (internal user ID `12345` at the Missourian) visits the Joplin Globe, her home base generates:

```
networkUserId = "HB001-" + hash("12345" + "GLOBE" + secret_key)
             = "HB001-a7f3bc92e41d"
```

When Susan visits the Springfield News-Leader:

```
networkUserId = "HB001-" + hash("12345" + "NEWSLEADER" + secret_key)
             = "HB001-5e8912dc7b3a"
```

These IDs are:
- **Deterministic:** Susan always gets the same ID when visiting the Globe. Her session persists.
- **Unique per publisher:** The Globe ID and the News-Leader ID are completely different.
- **Opaque:** They contain no information about Susan's name, email, or any personal attribute.
- **Unlinkable:** The Globe and the News-Leader cannot determine that these IDs belong to the same person — unless the Missourian (Susan's home base) cooperates, which ITEGA rules prohibit.
- **Revocable:** The Missourian can unlink any of Susan's IDs at any time. Susan vanishes from that publisher's records.

This is not a novel invention — it implements what the W3C OIDC specification calls a **Pairwise Pseudonymous Identifier (PPID)**, codified in OIDC Core Section 8. What's notable is that Clickshare designed this exact mechanism in 1996, before the standard existed.

---

## The Wholesale-Retail Pricing Model

The Newshare Network uses a pricing model borrowed from physical retail:

```
                  Publisher                          Home Base
              (sets wholesale)                   (sets retail markup)

  The Joplin Globe says:                The Columbia Missourian says:
  "This article costs $0.05              "Our markup ratio is 1.4x
   wholesale to access."                  (40% margin on wholesale)."

                            ┌──────────┐
                            │  Result  │
                            └──────────┘

  Susan sees: "This article costs $0.07" (before she clicks)
  The Globe receives: $0.05 (wholesale)
  The Missourian keeps: $0.02 (retail margin)
  ITEGA receives: ~$0.001 (transaction fee)
```

**Why this matters:**
- Two users from different home bases may see **different prices for the same article** — just like the same toaster sells for different prices at different stores.
- Publishers control their wholesale pricing. Home bases control their retail markup. No one controls both.
- Home bases have a genuine business model: they capture margin by serving their subscribers well.
- ITEGA's transaction fee is analogous to Visa's interchange fee — a small percentage that funds network governance, not platform profit.

### Pricing Example: Three Users, One Article

The Joplin Globe publishes an investigative piece and sets `pageClass = $0.10` (wholesale).

| User | Home Base | Home Base markupRatio | User Sees (Retail) | Globe Gets | Home Base Keeps |
|------|-----------|----------------------|-------------------|-----------|----------------|
| Susan | Columbia Missourian | 1.4x | $0.14 | $0.10 | $0.04 |
| Tom | Springfield News-Leader | 1.2x | $0.12 | $0.10 | $0.02 |
| Maria | KC Public Library | 1.0x (no markup) | $0.10 | $0.10 | $0.00 |

The Globe doesn't know or care what retail price each user sees. It just gets its wholesale price. This is how free markets work.

---

## The NetworkGroupId: How Subscription Tiers Work

Instead of sharing subscription details, the network encodes a user's access rights as a **bitmask** — a single number that compactly represents multiple subscription attributes:

| Bit Value | Meaning |
|-----------|---------|
| 0 | Anonymous — accessing without login (pre-registration meter) |
| 1 | Group Account — IP-based or access-key |
| 2 | Registered — logged in with individual account |
| 4 | Print Subscriber |
| 8 | Digital / Web Subscriber |
| 16 | Data / Special Content Subscriber |
| 1024 | Complimentary Subscriber |
| 2048 | Controlled (free) Subscriber |
| 4096 | Paid Subscriber |
| 8192 | Trial Subscriber |
| 16384 | Site / Group Subscriber (corporate, university, library) |

Bits combine with bitwise OR. Examples:

| NetworkGroupId | Meaning |
|----------------|---------|
| `2` | Registered (free account, no subscription) |
| `4104` | Paid Subscriber (4096) + Print Subscriber (4) |
| `4106` | Paid (4096) + Print (4) + Registered (2) |
| `8200` | Trial (8192) + Digital (8) |
| `16386` | Site/Group (16384) + Registered (2) |

Each publisher maps these bits to their own access control rules. A publisher might say: "Bit 4096 (Paid) and Bit 8 (Digital) get full access. Bit 8192 (Trial) gets 5 articles. Bit 0 (Anonymous) gets 3 free articles before a meter."

---

## Authentication Flow: Step by Step

```
  USER                    PUBLISHER B              ALS                    HOME BASE
   │                         │                      │                        │
   │  1. Click article       │                      │                        │
   │ ──────────────────────► │                      │                        │
   │                         │                      │                        │
   │  2. No local session.   │                      │                        │
   │     Show "Network Login"│                      │                        │
   │ ◄────────────────────── │                      │                        │
   │                         │                      │                        │
   │  3. Click "Network Login"                      │                        │
   │ ─────────────────────────────────────────────► │                        │
   │                         │                      │                        │
   │                         │         4. Home-site discovery                │
   │                         │            (header hint or user picks from list) │
   │                         │                      │                        │
   │  5. Redirect to home base login                │                        │
   │ ◄────────────────────────────────────────────────────────────────────── │
   │                         │                      │                        │
   │  6. User authenticates (username/password/passkey)                      │
   │ ─────────────────────────────────────────────────────────────────────► │
   │                         │                      │                        │
   │                         │                      │  7. Home base generates │
   │                         │                      │     PPID + GroupId      │
   │                         │                      │ ◄───────────────────── │
   │                         │                      │                        │
   │                         │  8. ALS validates     │                        │
   │                         │     token, issues     │                        │
   │                         │     sessionToken      │                        │
   │                         │ ◄─────────────────── │                        │
   │                         │                      │                        │
   │  9. Publisher B receives networkUserId +       │                        │
   │     networkGroupId, maps to access controls    │                        │
   │ ◄────────────────────── │                      │                        │
   │                         │                      │                        │
   │  CONTENT SERVED         │  10. ALS logs event  │                        │
   │                         │ ────────────────────►│                        │
```

Once authenticated, Publisher B caches the session. When it expires, the flow repeats transparently — Susan doesn't see a login screen again as long as she's logged into her home base.

---

## What Gets Logged (and What Doesn't)

Every content access event creates one log record. Here is exactly what it contains:

| Field | Example Value | Contains PII? |
|-------|--------------|---------------|
| `timestamp` | `2026-09-15T14:32:07Z` | No |
| `networkUserId` | `HB001-a7f3bc92e41d` | No (opaque) |
| `homeBaseId` | `HB001` | No |
| `pubMbrId` | `PUB003` | No |
| `resourceId` | `https://joplinglobe.com/investigation/water-quality` | No |
| `pageClass` | `0.10` | No |
| `serviceClass` | `4104` | No |
| `markupRatio` | `1.4` | No |
| `eventType` | `content_access` | No |
| `sessionId` | `sess-8f2a3b7c` | No |

**What is NOT in the log:** Susan's name. Her email. Her IP address. Her browser fingerprint. Her reading history at other publishers. Nothing that could identify her as a human being.

### Who sees what:

| Recipient | What They Get |
|-----------|--------------|
| **Susan's home base (Missourian)** | Full clickstream: every article Susan read at every publisher. This is for billing Susan and understanding her usage. |
| **The Joplin Globe** | Aggregated totals: "Home base HB001 sent us 47 readers who accessed 312 articles this week, total wholesale value $15.60." The Globe **cannot** see individual user activity. |
| **The ALS operator** | The raw log data above — but with no ability to connect `HB001-a7f3bc92e41d` to a real person. |
| **ITEGA** | Nothing. ITEGA does not operate services and does not receive user data. |
| **Third parties** | Nothing. Ever. Log data is never sold, shared, or provided to any third party. |

---

## Settlement: How Publishers Get Paid

Settlement runs weekly (configurable) as a batch process — NOT in real time. This is deliberate: it separates performance-critical authentication from financial processing.

### Weekly Settlement Example

During one week, the ALS logs these events:

| Home Base | Publisher | Events | Total Wholesale |
|-----------|----------|--------|----------------|
| Missourian (HB001) | Joplin Globe (PUB003) | 47 accesses | $4.70 |
| Missourian (HB001) | Springfield N-L (PUB005) | 12 accesses | $0.60 |
| News-Leader (HB005) | Joplin Globe (PUB003) | 23 accesses | $2.30 |
| News-Leader (HB005) | Missourian (PUB001) | 8 accesses | $0.40 |

Settlement produces:

```
DEBITS (home bases owe):
  Missourian:  $5.30  (for their users' consumption across the network)
  News-Leader: $2.70

CREDITS (publishers are owed):
  Joplin Globe:  $7.00  ($4.70 from Missourian users + $2.30 from N-L users)
  Springfield:   $0.60
  Missourian:    $0.40  (for content consumed by News-Leader users)

ITEGA FEE (1.5%):
  $0.12

VERIFICATION:
  Total debits ($8.00) = Total credits ($8.00) ✓
  ITEGA fee deducted from total before distribution

ACH TRANSFERS:
  Missourian bank account: debit $5.30
  News-Leader bank account: debit $2.70
  Joplin Globe bank account: credit $6.90 ($7.00 - $0.10 share of ITEGA fee)
  Springfield bank account: credit $0.59
  Missourian bank account: credit $0.39
  ITEGA bank account: credit $0.12
```

---

## Technical Architecture

### Deployment for Missouri Pilot

The prototype runs on two DigitalOcean 4GB droplets (~$49/month total). Keycloak is separated from the ALS services because its Java JVM idles at 400-500MB and both benefit from dedicated resources:

```
VPS 1: Home Base IdSP ($24/mo)       VPS 2: ALS Services ($24/mo)
auth.newshare.example                 als.newshare.example
┌────────────────────────┐            ┌───────────────────────────────┐
│ Keycloak 26.x          │            │ FastAPI: ALS Auth Service     │
│  - OIDC Provider       │◄──────────│  - Token validation           │
│  - Built-in PPID       │            │  - Home-site routing          │
│  - Custom SPI mapper   │            │  - Session token issuance     │
│                        │            │                               │
│ PostgreSQL 16          │            │ FastAPI: ALS Logging Service  │
│  - keycloak DB         │            │  - Event ingestion            │
│  - newshare_profiles   │            │  - Usage reports              │
│  - PPID mappings       │            │                               │
└────────────────────────┘            │ PostgreSQL 16 + TimescaleDB   │
                                      │ Python: Settlement (cron)     │
                                      │ React: User Dashboard         │
                                      │ Nginx: TLS termination        │
                                      └───────────────────────────────┘
                                                    │
           ┌────────────────┬───────────────────────┼────────────────┐
           ▼                ▼                        ▼                ▼
  ┌──────────────┐ ┌──────────────┐       ┌──────────────┐ ┌──────────────┐
  │ Columbia      │ │ Joplin       │       │ Springfield   │ │ Other MPA    │
  │ Missourian   │ │ Globe        │       │ News-Leader   │ │ Newspapers   │
  │ WordPress    │ │ WordPress    │       │ WordPress     │ │ WordPress    │
  │ + Newshare   │ │ + Newshare   │       │ + Newshare    │ │ + Newshare   │
  │   Plugin     │ │   Plugin     │       │   Plugin      │ │   Plugin     │
  └──────────────┘ └──────────────┘       └──────────────┘ └──────────────┘
              3–5 participating Missouri newspapers via MPA
```

*(The original spec envisioned a single VM at $300-$500/month. The prototype implementation splits into two smaller VPSes at $49/month total, which is cheaper and gives Keycloak its own memory headroom.)*

### Components

| Component | What It Does | Technology |
|-----------|-------------|------------|
| **Home Base (IdSP)** | Authenticates users, generates PPIDs, stores profiles | Keycloak 26.x + PostgreSQL 16 |
| **ALS Auth Service** | Validates JWT tokens in real time, routes authentication flows | Python 3.12 / FastAPI sidecar |
| **ALS Logging Service** | Records every content access event in Extended Common Log Format | Python 3.12 / FastAPI + TimescaleDB |
| **ALS Settlement Service** | Weekly batch: aggregates logs, computes debits/credits, generates reports | Python 3.12 batch script |
| **Publisher Plugin** | "Network Login" button, OIDC Relying Party, content tagging | WordPress plugin (PHP) |
| **Network Discovery** | Directory of certified home bases and publishers | OIDC Discovery endpoint + WebFinger |
| **User Dashboard** | Shows users their session, reading history, balance, privacy controls | React + TypeScript |

See `plans/` directory for detailed implementation plans for each component.

---

## Protocol Stack

| Function | Protocol / Standard | Why This One |
|----------|-------------------|--------------|
| Core SSO federation | **OpenID Connect 1.0** (Authorization Code Flow) | The dominant SSO standard. Maps directly onto the 1996 TVS token architecture. |
| Token format | **JSON Web Token (JWT)**, RFC 7519 | Industry standard. The modern equivalent of the TVS authentication token. |
| Home-site discovery | **OIDC Discovery** + **WebFinger** (RFC 7033) | How the network finds which home base a user belongs to. |
| Pairwise user IDs | **OIDC PPID** (Core spec Section 8) | Prevents cross-site user correlation. A recognized W3C standard. |
| Rich identity claims | **W3C Verifiable Credentials** (VC Data Model 2.0) | Portable, user-controlled identity attributes. |
| Sensitive claim encryption | **JWE** (RFC 7516) | Protects sensitive claims inside tokens. |
| Subscription tier encoding | **NetworkGroupId** (custom bitmask claim) | Compact, extensible encoding of access rights in JWT. |
| User profile attributes | **Schema.org/Person** + **Internet2 eduPerson** | Standard vocabularies for personal attributes. |
| Content rights tagging | **Really Simple Licensing (RSL)** standard | Uniform content rights metadata, including for AI model usage tracking. |
| Transport security | **TLS 1.3** mandatory | All network connections encrypted. |

---

## Technology Stack

| Component | Recommended Technology | Alternatives |
|-----------|----------------------|-------------|
| OIDC Identity Provider | **Keycloak** (Java, Apache 2.0 license) | Authentik (Python/Go) |
| User Profile Store | **PostgreSQL 16** with Clickshare schema | Apache Unomi (W3C Context API) |
| ALS Auth Service | **FastAPI** (Python) or **Fastify** (Node.js) sidecar | Built into Keycloak |
| ALS Logging | **TimescaleDB** (PostgreSQL extension) | ClickHouse |
| ALS Settlement | **Python 3.12** batch script | Node.js |
| Payment Processing | **Stripe Connect** (ACH) | Dwolla, Stripe Treasury, direct bank ACH |
| Publisher Integration | **WordPress plugin** (PHP 8.1+) | Drupal module (future) |
| User Dashboard | **React 19** + TypeScript + Vite + Tailwind | Astro + React islands |
| Content Tagging | **JSON-LD** in HTML | Standard RSL metadata |

Design philosophy (from spec): "Built from open-source components wherever possible, minimizing proprietary lock-in. The goal is a stack that a small team of developers familiar with modern web infrastructure can deploy in weeks, not months."

---

## Missouri Pilot: Proof of Concept

### Objective

Demonstrate the core end-to-end architecture with real publishers and real readers: a user creates one account at a home base publisher, visits a second participating publisher, is recognized without re-registering, and a transaction event is logged and settled.

### Partners

| Role | Organization |
|------|-------------|
| Institutional Host & Academic Partner | Donald W. Reynolds Journalism Institute (RJI), University of Missouri |
| Industry Convener | Missouri Press Association (MPA) |
| Technical Operator | PubGen.AI (Sho Rust, CEO) — Cape Girardeau, MO |
| Technical Architect | Clickshare Service Corp. (Richard Lerner, CEO) — Amherst, MA |
| Governing Authority | ITEGA |
| Participating Publishers | 3–5 independent Missouri newspapers (mix of small daily, weekly, digital outlets) |

### Success Criteria

1. A user creates one account at Publisher A (home base) and accesses content at Publisher B without re-registering.
2. Publisher B receives the user's NetworkGroupId and serves content according to subscription tier.
3. The ALS logs the access event with an opaque user ID — no PII transmitted.
4. Publisher B cannot identify the user's real identity from network data.
5. Weekly settlement runs produce accurate usage reports and simulated ACH settlement records.
6. At least **50 real users** complete the cross-publisher authentication flow during the pilot period.

### Timeline

| Phase | Duration | Activities |
|-------|----------|------------|
| Months 1–2 | Setup | Deploy OIDC infrastructure. Configure demo home base. Build WordPress plugin v1. Recruit 3 MPA newspapers. |
| Months 3–4 | Integration | Deploy plugin at participating newspapers. Onboard pilot users. Stand up logging service and weekly settlement. |
| Months 5–6 | Operations | Live pilot with real readers. Monitor, debug, iterate. Collect qualitative feedback. |
| Months 7–8 | Expansion | Expand to additional publishers if successful. Begin UDEX (User Data Exchange) architecture planning. |
| Month 18 | Evaluation | Produce public pilot report. Brief funders and potential Phase 2 partners. |

### Budget

| Item | Amount |
|------|--------|
| Technical Development (2 developers, 12 months) | $180,000 |
| Project Director | $75,000 |
| Project Coordination (Densmore, 0.33 FTE, 18 months) | $35,000 |
| Richard Lerner / Technical Architecture | $30,000 |
| Cloud Infrastructure ($300/month x 18 months) | $5,400 |
| Publisher Integration Support (small grants to newspapers) | $15,000 |
| Legal (membership agreements, pilot terms) | $15,000 |
| Travel and Convenings | $18,000 |
| Evaluation and Reporting | $12,000 |
| Contingency (10%) | $19,600 |
| **TOTAL** | **$400,000** |

Phase 2 (broader rollout + UDEX): ~$2M over 3 years. Not part of this request.

---

## Prototype: Low-Cost Demo ($49/month)

In addition to the full Missouri Pilot architecture, this repository contains a **working prototype** designed to demonstrate the complete flow on two cheap VPS instances.

### Prototype Architecture

```
VPS 1: Home Base IdSP ($24/mo)       VPS 2: ALS Services ($24/mo)
auth.newshare.example                 als.newshare.example
┌────────────────────────┐            ┌───────────────────────────────┐
│ Keycloak 26.x          │            │ FastAPI: ALS Auth Service     │
│  - OIDC Provider       │◄──────────│  - Token validation           │
│  - Built-in PPID       │            │  - Home-site routing          │
│  - Custom SPI mapper   │            │  - Session token issuance     │
│                        │            │                               │
│ PostgreSQL 16          │            │ FastAPI: ALS Logging Service  │
│  - User profiles       │            │  - Event ingestion            │
│  - PPID mappings       │            │  - Usage reports              │
└────────────────────────┘            │                               │
                                      │ PostgreSQL 16 + TimescaleDB   │
                                      │ Python: Settlement (cron)     │
                                      │ React: User Dashboard         │
                                      │ Nginx: Reverse proxy + TLS    │
                                      └───────────────────────────────┘
                                                    │
           ┌────────────────┬───────────────────────┼────────────────┐
           ▼                ▼                        ▼                ▼
  ┌──────────────┐ ┌──────────────┐       ┌──────────────┐ ┌──────────────┐
  │ WP Site 1    │ │ WP Site 2    │       │ WP Site 3    │ │ WP Site 4    │
  │ + Plugin     │ │ + Plugin     │       │ + Plugin     │ │ + Plugin     │
  └──────────────┘ └──────────────┘       └──────────────┘ └──────────────┘
           Existing WordPress sites with Newshare plugin
```

### Key Decisions

- **Keycloak** (not Authentik) — ships with built-in `SHA256PairwiseSubMapper` for PPID. A ~120-line custom Java SPI plugin reformats the pairwise `sub` into Newshare's `[HomeBaseID]-[hash]` format.
- **FastAPI** for all ALS backend services — lightweight, async, same language as settlement.
- **Simulated settlement** — generates reports showing what would be debited/credited, no real money moves.
- **Two VPS** instead of one — Keycloak idles at 400-500MB; separating it from TimescaleDB keeps both under 4GB comfortably.

### Running the Prototype Demo

1. Register a test user at `https://auth.newshare.example/realms/newshare/account`
2. Set their `networkGroupId` to `4104` (Paid + Print) in Keycloak Admin
3. Visit a gated article on any WordPress site with the plugin installed
4. Click "Log in with your news network account"
5. Authenticate through ALS → Keycloak → back to publisher with sessionToken
6. Content is served; event is logged to TimescaleDB
7. Visit a second publisher site — verify a **different** `networkUserId` (PPID isolation)
8. Run `python settle.py` to generate settlement reports

### What's Simulated vs. Real

| Component | Real | Simulated |
|-----------|------|-----------|
| User registration and authentication | Real (Keycloak OIDC) | — |
| PPID generation (different ID per publisher) | Real (Keycloak built-in) | — |
| NetworkGroupId bitmask access control | Real (WordPress plugin) | — |
| Content access event logging | Real (TimescaleDB) | — |
| RSL content tagging (JSON-LD) | Real (WordPress plugin) | — |
| Settlement (debits, credits, ITEGA fee) | — | Reports only, no ACH |
| ACH bank transfers | — | Not implemented |
| MFA / Passkeys | — | Password auth only (Keycloak supports TOTP, can enable later) |

### VPS Resource Estimates

These are initial estimates based on component defaults. Revisit once the code is running under real load — actual usage may differ.

**VPS 1 — Home Base IdSP** (DigitalOcean 4GB RAM / 2 vCPU — $24/mo):

| Process | Estimated RAM | Notes |
|---------|---------------|-------|
| Keycloak JVM (`-Xmx768m`) | 800-900 MB | Java; idles ~500MB, can spike to 1.2GB+ under auth load |
| PostgreSQL 16 | 200-300 MB | Two databases: `keycloak` + `newshare_profiles` |
| OS + Nginx | ~300 MB | Ubuntu 24.04 baseline |
| **Total at idle** | **~1.3-1.5 GB** | Leaves ~2.5 GB headroom on 4GB droplet |

Keycloak is the memory bottleneck (it's Java). A 2GB droplet ($12/mo) works with `-Xmx512m` for a handful of demo users but leaves almost no headroom for spikes. 4GB is the safe choice for anything beyond trivial use.

**VPS 2 — ALS Services** (DigitalOcean 4GB RAM / 2 vCPU — $24/mo):

| Process | Estimated RAM | Notes |
|---------|---------------|-------|
| PostgreSQL + TimescaleDB | 200-300 MB | Two databases: `als_logs` + `als_settlement` |
| FastAPI Auth Service | 50-80 MB | Python; lightweight async workers |
| FastAPI Logging Service | 50-80 MB | Python; lightweight async workers |
| Nginx + static files | ~30 MB | Serves dashboard + Network Discovery JSON |
| OS | ~300 MB | Ubuntu 24.04 baseline |
| **Total at idle** | **~650-800 MB** | Significantly overprovisioned at 4GB |

VPS 2 is well within a 2GB droplet ($12/mo). Kept at 4GB for headroom as TimescaleDB grows or if services are added later. Can downsize to save $12/mo.

**Cost options:**

| Configuration | Monthly Cost |
|---------------|-------------|
| Both at 4GB (current) | ~$49/mo |
| VPS 1 at 4GB + VPS 2 at 2GB | ~$37/mo |
| Both at 2GB (tight for Keycloak) | ~$25/mo |

---

## Project Structure

```
ITEGA/
├── CLAUDE.md                          ← Instructions for Claude Code
├── README.md                          ← This file
├── docs/
│   └── source-pdfs/                   ← Original documents from Bill Densmore
│       ├── claude-itega-newshare-tech-spec-02-22-26b-1110pest.pdf  (20pp, tech spec)
│       ├── claude-itega-funder-brief-02-23-26b-1201aest.pdf        (9pp, funder brief)
│       ├── claude-itega-chat-02-22-26b.-ORIG.pdf                   (20+pp, chat transcript)
│       └── Claude AI chat, funder pitch and tech for ITEGA_Newshare_Missouri.pdf
├── plans/                             ← Detailed server/component implementation plans
│   ├── 00-system-architecture-overview.md
│   ├── 01-home-base-idsp-server.md
│   ├── 02-als-authentication-service.md
│   ├── 03-als-logging-service.md
│   ├── 04-als-settlement-service.md
│   ├── 05-publisher-wordpress-plugin.md
│   ├── 06-network-discovery-service.md
│   └── 07-user-dashboard.md
├── src/                               ← Prototype source code (~3,400 lines)
│   ├── keycloak-spi/                  ← Custom Keycloak protocol mapper (Java, ~140 lines)
│   ├── als-auth/                      ← ALS Auth Service (Python/FastAPI, main.py)
│   ├── als-logging/                   ← ALS Logging Service (Python/FastAPI, main.py)
│   ├── als-settlement/                ← Settlement batch script (Python, settle.py)
│   ├── wordpress-plugin/              ← newshare-network WordPress plugin (PHP, 8 classes)
│   └── dashboard/                     ← User Dashboard (React 19/TypeScript/Vite/Tailwind 3)
├── infra/                             ← Deployment infrastructure
│   ├── vps1/                          ← Docker Compose + Nginx for Home Base VPS
│   ├── vps2/                          ← Docker Compose + Nginx for ALS VPS
│   └── sql/                           ← Database migration scripts
└── research/                          ← Research notes and analysis (placeholder)
```

---

## Competitive Landscape

| Solution | How Newshare Differs |
|----------|---------------------|
| **Piano / Pico / Zuora** | Commercial paywalls and subscription management. Single-publisher silos. No cross-publisher identity federation. No user privacy by design. Profit motive conflicts with publisher interests. |
| **Google / Meta login ("Sign in with Google")** | User identity owned by platform, not publisher. Platform learns cross-site behavior. No settlement or payment capability. Creates dependency on for-profit surveillance infrastructure. |
| **Apple News+** | Closed ecosystem. Apple captures margin. Publishers lose direct reader relationship. No cross-publisher micropayment or flexible pricing. |
| **Solid / WebID (Berners-Lee)** | Strong privacy model; user-controlled data pods. No journalism-specific settlement or payment layer. Very early ecosystem; limited publisher adoption. Complementary rather than competing. |
| **InCommon / Internet2** | Closest operational analog for higher education. ITEGA draws on this model explicitly. InCommon does not serve commercial news publishing or include a settlement/payment layer. |

---

## History and Lineage

| Year | Milestone |
|------|-----------|
| 1993 | Bill Densmore founds what becomes Clickshare Service Corp. |
| 1996 | Clickshare deploys working four-party federated identity and micropayment network — the Token Validation Service (TVS). Built on modified NCSA httpd. No cookies, no central identity database. |
| 2000 | U.S. Patent filed: "Managing Transactions on a Network: Four or More Parties" |
| 2008 | Patent granted (No. 7,324,972). Densmore becomes RJI Fellow at University of Missouri. |
| 2009 | Densmore publishes "From Paper to Persona" at RJI. |
| 2017 | ITEGA incorporated as California 501(c)(3). |
| 2018–2021 | Craig Newmark Philanthropies funds ITEGA convenings in Chicago, Brooklyn, DC. |
| 2021 | ITEGA publishes "Identity, Advertising and the Future of Journalism: A Call to Action" white paper. |
| 2022 | U.S. Patent 7,324,972 expires. Architecture enters public domain. |
| 2025 | RSL (Really Simple Licensing) standard established. |
| 2025–2026 | Richard Lerner and Bill Densmore modernize architecture to OIDC, JWT, W3C VC. Full technical specification completed January 2026. |
| 2026 (Feb) | Newshare Network Technical Architecture v1.0 Draft published. Funding request for Missouri pilot circulated. |

---

## Key People

| Person | Role | Background |
|--------|------|------------|
| **Bill Densmore** | Founder & Interim Executive Director, ITEGA | Career journalist and tech entrepreneur. AP editor/writer. Founded Clickshare 1993. RJI Fellow 2008-2009. Based in Williamstown, MA. |
| **Richard Lerner** | CEO, Clickshare Service Corp. Technical Architect. | Carnegie Mellon University PhD in Computer Science. Co-inventor, U.S. Patent 7,324,972. Co-author of 2026 technical specification. Based in Amherst, MA. |
| **Jo Ellen Green Kaiser** | Board Chair, ITEGA | Non-executive lead of ITEGA governance. Moderated 2021 webinar series. |
| **Sho Rust** | CEO, PubGen.AI. Technical Operator for pilot. | Develops unified CMS platform for local news publishers. Based in Cape Girardeau, MO. |

---

## Source Documents

The definitive technical reference is the **Newshare Network Technical Architecture and Specification v1.0 Draft** (February 2026), authored by Bill Densmore and Richard Lerner. This 20-page document covers:

- Section 1: Background and context (problem, history, why now)
- Section 2: System architecture (four-party model, auth flow, PPID, NetworkGroupId)
- Section 3: Protocol specifications (OIDC, JWT, user schema, RSL, wholesale-retail pricing)
- Section 4: Logging and settlement service (design principles, log format, settlement process)
- Section 5: Recommended technology stack (Keycloak, PostgreSQL, TimescaleDB, WordPress, React)
- Section 6: Governance, certification, and membership (ITEGA's role, tiers, sanctions)
- Section 7: Missouri pilot (objective, participants, success criteria, timeline, budget)
- Section 8: Funding strategy (target funders, sustainability model)
- Section 9: Competitive differentiation
- Section 10: Technical references and prior work

The **funder brief** is a 9-page non-technical summary of the above, written for foundation and academic partners. It requests $400,000 over 18 months.

The **chat transcript** is a 20+ page record of Bill Densmore's February 21-22, 2026 conversation with Claude Sonnet 4.6, which produced the tech spec and funder brief. It provides additional context on design decisions.

---

## Peer Review Feedback

In February–March 2026, the Newshare Network technical documents were reviewed by two expert advisors:

### Drummond Reed — Decentralized Identity Pioneer

**Drummond Reed** (Chief Trust Officer, Evernym; co-author, Respect Trust Framework) reviewed the architecture and recommended ITEGA consider becoming a **Verifiable Trust Network (VTN)** using decentralized digital identity standards (DIDs, Verifiable Credentials, Trust Over IP). He argues that OIDC-based federated identity is being superseded by wallet-based decentralized identity, driven by AI agent interoperability needs. He specifically suggested partnering with the **First Person Cooperative**, which is building VTNs across multiple sectors and plans to approach Adobe's **Content Authenticity Initiative** about a media-industry VTN.

Key point: *"With this new infrastructure, you could realize your vision of an international news network in which any reader would have frictionless authenticated access and integrated micropayments."*

### Don Marti — ITEGA Advisor, Open Source/Web Standards

**Don Marti** (longtime ITEGA advisor) recommended simplifying to the **minimum demo-able version** using tools already present on publisher sites. He warned that independent publishers have "extremely brittle tech stacks" and suggested considering advertiser funding to motivate publisher participation.

Key point: *"It should be possible to simplify and work out from one page of an understandable project to get a very basic demo going."*

### Recommended Path

Both perspectives are complementary. The recommended strategy is **dual-track:**

1. **Ship the OIDC pilot now** — follow Don's advice and demonstrate the minimum viable cross-publisher authentication with real Missouri newspapers
2. **Plan the VTN evolution** — follow Drummond's advice and engage with the First Person Cooperative about a future migration to decentralized identity

The current architecture already incorporates several decentralized principles (PPID, no central identity database, W3C Verifiable Credentials in protocol stack, no cookies) that make this migration feasible.

See [`docs/peer-review-synthesis.md`](docs/peer-review-synthesis.md) for the full analysis.

---

## Evolution Path: From OIDC to Verifiable Trust Networks

The Newshare four-party model maps nearly one-to-one onto the Trust Over IP (ToIP) Verifiable Trust Network concept:

| Newshare Role | VTN Equivalent |
|--------------|---------------|
| ITEGA (Governing Authority) | VTN Governance Authority |
| Home Base (IdSP) | Credential Issuer / Wallet Provider |
| Publisher (Content Provider) | Verifier / Relying Party |
| ALS (Auth/Logging/Settlement) | Trust Registry + Verification Service |
| End User (Reader) | Holder (of Verifiable Credentials) |

**Phase 1 (now):** OIDC-based pilot proves the business model and governance with real publishers and users.
**Phase 2+:** Migrate to DID/VC-based authentication as the ecosystem matures, preserving the four-party model and all business logic.

Key standards to watch: W3C DIDs, W3C Verifiable Credentials, Trust Over IP Foundation, First Person Cooperative, Content Authenticity Initiative (C2PA).

---

## Bill Densmore's 7 Peer Review Questions

Bill Densmore has asked technical reviewers (Don Marti, Rick Lerner) to assess:

1. **Marketplace assertions:** Are the assertions of marketplace status Claude makes in the chat and documents reasonable? Do they build a case for ITEGA?
2. **Protocol selections:** Are the protocol selections recommended on Page 7 of the tech spec appropriate and a state-of-the-art updating of the 1996 proof of concept?
3. **Technology stack:** Evaluate or provide impressions of the Recommended Technology Stack from Page 12 of the tech spec as to purpose fit or other matters.
4. **Deployment architecture:** Comment on the Deployment Architecture for the pilot at the bottom of Page 12.
5. **Missouri Pilot UX:** If you have knowledge, is the Missouri Pilot description of user experience from Page 16 consistent with the expectations of partners PubGen.AI, RJI, and the Missouri Press Association?
6. *(blank in original)*
7. **Competitive analysis:** Is the competitive analysis at Page 19 adequate/accurate?
