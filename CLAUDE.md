# CLAUDE.md — Project Instructions for Claude Code

## Project: ITEGA / Newshare Network

This repository contains the technical review, planning documents, and working prototype
implementation for the Newshare Network, governed by ITEGA.

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
│   ├── STATUS.md               ← START HERE. Living handoff: state, plan, decisions
│   ├── vps-setup-record.md     ← How the servers were built, and what went wrong
│   ├── monitoring.md           ← Beszel hub and agents
│   ├── publisher-sites.md      ← The three WordPress publisher sites
│   ├── publisher-onboarding.md ← How a real newspaper joins; domain proof
│   ├── demo-script-gap-analysis.md ← Aug 25 demo script vs. the code; open questions
│   ├── peer-review-synthesis.md ← Synthesis of Drummond Reed + Don Marti feedback
│   ├── response-to-bill.md     ← Summary for Bill Densmore
│   └── source-pdfs/            ← Original documents from Bill Densmore
├── reference/                  ← GITIGNORED. Source PDFs, correspondence, and Bill's
│                                  working demo scripts. Local only — this repo is public.
├── plans/
│   ├── 00-system-architecture-overview.md
│   ├── 01-home-base-idsp-server.md
│   ├── 02-als-authentication-service.md
│   ├── 03-als-logging-service.md
│   ├── 04-als-settlement-service.md
│   ├── 05-publisher-wordpress-plugin.md
│   ├── 06-network-discovery-service.md
│   └── 07-user-dashboard.md
├── src/
│   ├── keycloak-spi/           ← Custom Keycloak protocol mapper (Java)
│   ├── als-auth/               ← ALS Auth Service (Python/FastAPI)
│   ├── als-logging/            ← ALS Logging Service (Python/FastAPI)
│   ├── als-settlement/         ← Settlement batch script (Python)
│   ├── network-discovery/      ← Network Discovery Service (Python/FastAPI)
│   ├── wordpress-plugin/       ← newshare-network WordPress plugin (PHP)
│   └── dashboard/              ← User Dashboard (React/TypeScript/Vite)
├── infra/
│   ├── vps1/                   ← Docker Compose + Nginx for Home Base VPS
│   ├── vps2/                   ← Docker Compose + Nginx for ALS VPS
│   └── sql/                    ← Database migration scripts
└── research/
```

## Prototype Architecture — LIVE as of Aug 11, 2026

Running on **two Hetzner cloud servers in Falkenstein** (~$15.48/mo total),
AlmaLinux 10, CSF firewall, Apache reverse proxy, Docker Compose:

- **VPS 1** (`auth.itega.org`): Keycloak 26.x (three realms) + PostgreSQL 16 + three Retail Agents
- **VPS 2** (`als.itega.org`): FastAPI services + TimescaleDB + React dashboard

Live hostnames: `auth`, `agent-c`, `agent-demo` (VPS 1); `als`, `network`,
`dashboard` (VPS 2) — all under `itega.org`, all on Let's Encrypt with automated
renewal. The third Retail Agent is served at `auth.itega.org/agent-wesmc`
rather than its own hostname; the registry is the authority on which agent
belongs to which home base, so read `agent_url` from
`network.itega.org/discovery/home-bases` rather than assuming the pattern.

**See `docs/vps-setup-record.md`** for exactly how these were built, including
the failures worth not repeating (Alma's missing kernel modules, CSF's dead
download host, the CSF/Docker iptables conflict, Keycloak rejecting JSON
comments).

**The Retail Agent runs on the home base host, never the ITEGA host.** It holds
the markup ratio and decides purchases; ITEGA may see neither. This is an
architectural rule, not a deployment convenience.

**Three publishers, three home bases, and each organisation is both.**
`barharbor.info`, `northberkshire.org` and `wesmc.org` all run the plugin, and
each is also a certified home base (realms `publisher-c`, `newshare`, `wesmc`
respectively). That overlap is deliberate: Bill's Definitions allow a member to
act as ASP, CMS or both, and a demonstration with five organisations in it is
harder to follow than one with three. See `docs/publisher-sites.md`.

Markups differ per home base — 1.10, 1.40 and 1.25 — so one wholesale nickel
produces three retail prices. Every published article carries an explicit price;
do not rely on the site default alone, which is what hid issue #18.

The one deliberate exception: **barharbor.info's public notices are free** —
road closures, meeting listings, hearing notices, the twenty-one such items from
2025 and 2026. Public notices sit outside the paywall and reporting sits behind
it, which is what a newspaper would actually do, and it stops the meter landing
a demonstration on an expired road-closure notice. The archive stays priced, at
any age: a reader arriving from a search result onto a five-year-old story is a
read the publisher is owed for, `archive_is_metered` asserts it sixty articles
deep on every site, and forgetting that is what produced issue #18.
Settlement is **simulated only** — reports generated, no real money moves.

**wesmc.org's articles are about real, verifiable events**, written originally
and attributed rather than copied — a demonstration arguing that journalism
should be paid for cannot be built on invented reporting or on republished
copy. Fourteen of them were once unpublished here on the assumption that a run
of crime headlines naming real venues had to be fabricated. Every one checked
out against mainstream coverage. Verify before removing, and prefer drafting to
deleting.

## The explainer films

`scratchpad/deck1/` builds a 120-slide deck and renders it as narrated video —
a 12-minute cut for circulation and a 28-minute full version. Both are served,
with the slides, from the unlisted preview at
`dashboard.itega.org/preview-f45033ceaf/`.

```bash
make_video.py frames     # screenshot every slide (parallel, ~90s)
make_video.py speak      # ElevenLabs narration, cached per slide id
make_video.py assemble   # the full film
make_video.py short      # the cut, from the same frames and speech
make_video.py spec       # rewrite the .bed.json timings without re-encoding
verify.py <film>.mp4     # check the finished file
```

Four things about this pipeline are load-bearing, each learned by shipping the
bug:

- **Use `chrome-headless-shell`, not Google Chrome.** Chrome 151 removed the old
  headless mode; `--headless --screenshot` launches the full browser and hangs
  forever, on a one-line page as readily as on a deck.
- **Slice the per-slide page at `<body>`, not at the nav rail.** The rail is
  appended *after* the slides, so cutting there puts all 120 slides in every
  page and every screenshot returns slide one — at a plausible file size.
- **Slide ids must be unique.** Narration is cached per id, so a duplicate makes
  one slide speak another's script, fluently and about the wrong picture.
- **The narration in the speaker notes is the script.** There is no second copy
  to drift out of step.

`verify.py` rebuilds the music bed and subtracts it from the finished film: if
the bed is present and aligned it cancels. Measuring total loudness cannot work
— the narration runs ~18 dB above the bed and swamps it.

## VPS Resources — measured, not estimated

Both hosts are Hetzner, Falkenstein, AlmaLinux 10. **$15.48/month for the pair.**

**VPS 1 — Home Base IdSP** (`cx33`, 8 GB / 4 vCPU — $8.99/mo): 1.7 GB in use of
7.3 GB. Keycloak 711 MB, Postgres 30 MB, the two Retail Agents 86 MB together.
Keycloak is the only process worth sizing around.

**VPS 2 — ALS Services** (`cx23`, 4 GB / 2 vCPU — $6.49/mo): 1.0 GB in use of
3.5 GB. TimescaleDB 64 MB, ALS Auth 56 MB, Logging 39 MB, Discovery 36 MB.
Overprovisioned, but at $6.49 there is nothing worth recovering by shrinking it.

Earlier revisions of this file priced these at $24/mo each and offered a "$37/mo
cheaper alternative". Those were DigitalOcean figures from the planning phase and
never described anything that was actually bought. If a cost question comes up,
the real numbers are above and in `docs/server-specs.md`; Hetzner's US regions
cost roughly 3.4x the EU ones for identical hardware.

## Technology Stack (for code)

When building components, use these technologies:
- **Home Base IdSP:** Keycloak 26.x (Quarkus) + PostgreSQL 16. JVM tuned to `-Xms256m -Xmx768m` for 4GB VPS.
- **Keycloak SPI:** Custom Java protocol mapper (~120 lines) for `networkUserId` claim format. Extends `AbstractOIDCProtocolMapper`.
- **ALS Auth:** Python 3.12 + FastAPI. Issues its own `sessionToken` (RS256-signed JWT). Routes auth through Keycloak.
- **ALS Logging:** Python 3.12 + FastAPI. Writes to TimescaleDB `access_events` hypertable. Append-only.
- **ALS Settlement:** Python 3.12 batch script. Runs via weekly cron. Queries TimescaleDB, generates CSV/JSON reports.
- **Publisher Plugin:** WordPress plugin (PHP 8.1+) with OIDC RP flow through ALS (not directly to Keycloak).
- **User Dashboard:** React 19 + TypeScript + Vite + Tailwind CSS 3.
- **Content Tagging:** JSON-LD in HTML (`<script type="application/ld+json">`)
- **Infrastructure:** Docker Compose, Nginx with Let's Encrypt TLS, Cloudflare DNS.

## Key API Contracts

ALS Auth Service endpoints:
- `GET /auth/authorize` — initiates OIDC flow; resolves the visitor's home base or presents the chooser
- `GET /auth/select-home-base` — handles the chooser answer (name or Publishing Member ID)
- `GET /auth/callback` — handles OIDC callback, issues sessionToken
- `POST /auth/validate` — validates ALS-issued sessionTokens
- `GET /auth/home-bases` — lists certified home bases (sourced from Network Discovery)

ALS Logging Service endpoints:
- `POST /log/event` — ingests access events (fire-and-forget from publishers)
- `GET /log/report/home-base/{id}` — full clickstream for a home base
- `GET /log/report/publisher/{id}` — aggregated totals only for a publisher

Network Discovery Service endpoints:
- `GET /discovery/home-bases` — all certified home bases
- `GET /discovery/home-bases/resolve` — resolve a visitor to a home base (by id, name, or IP hint)
- `GET /discovery/home-bases/{id}` — a single certified home base
- `GET /discovery/publishers` — all certified publishers
- `GET /.well-known/webfinger` — WebFinger (RFC 7033) home-site discovery
- `GET /.well-known/newshare-network` — network-wide discovery document

sessionToken JWT claims: `iss`, `sub`, `aud`, `exp`, `iat`, `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `sessionId`

## Wholesale vs. retail — get this right

- `pageClass` **is** the wholesale price: what the publisher (Rights Owner) asks and is owed.
- `pageClass * markupRatio` is the **retail** price: what the home base (Retail Agent) bills its own user.
- **Only wholesale is settled through the ALS.** The markup is the home base's margin and never reaches the publisher.
- **Never disclose `markupRatio` or retail totals to publishers.** Per the pricing rules the Rights Owner does not need to know the markup and may not be permitted to.

Settlement previously had this inverted (crediting publishers the retail amount); see `docs/demo-script-gap-analysis.md`.

## Naming Conventions

- The consumer-facing brand is **"Newshare"** (or "Newshare Network")
- The governing body is **"ITEGA"**
- The technical/developer-facing brand can be **"NewsSSO"**
- **Publishers are named by letter: A, B, C.** Bill's demo script also calls them
  "Publisher 1/2/3" in places — those are the same parties (C == 3, A/B == 1/2), an
  artefact of the Definitions section being written before the later steps. Letters
  win everywhere: code, docs, registry data, demo copy.
- Use `networkUserId`, `homeBaseId`, `networkGroupId`, `pubMbrId`, `pageClass`, `markupRatio` for field names (camelCase, per the spec)
- Use `content_access`, `authentication`, `ad_view`, `subscription_credit`, `reward`, `logout` for event type enums
- Use `sessionId` for the ALS-issued session identifier claim in JWTs

## Key People

- **Bill Densmore** — ITEGA Founder & Interim Executive Director
- **Richard Lerner** — Clickshare CEO, co-inventor, lead architect (Carnegie Mellon PhD)
- **Sho Rust** — PubGen.AI CEO, technical operator for Missouri pilot
- **Matt Baya** — Project participant / reviewer
- **Drummond Reed** — Decentralized identity pioneer, Chief Trust Officer at Evernym, peer reviewer. Recommends VTN/DID evolution path.
- **Don Marti** — Longtime ITEGA advisor, open source/web standards expert, peer reviewer. Recommends simplifying to minimum demo-able version.
- **Glen Gerbush** — Developer Bill consulted. Argued the AI-generated codebase should be discarded rather than extended. Bill overrode this ("a bird in the hand") and chose to build on `src/` for Aug 25.

## Current work: the Aug 25 demo

**Start by reading `docs/STATUS.md`** — it is the living handoff document: what is
built, what is verified, what comes next in priority order, and the decisions already
settled with Bill. Keep it current as work lands.

Work is driven by Bill's demo script for the RJI/ITEGA roundtable on **Aug 25, 2026**.
The script lives in `reference/` (gitignored) and Bill revises it — check for the newest
`ITEGA-RJI-demo-script-*.md` before building. `docs/demo-script-gap-analysis.md` tracks
what is built, what is missing, and Bill's answers to the open questions.

**Build it really working.** A simulated or narrated demo is the fallback, not the goal.

### Test before you claim

Run both suites before showing the system to anyone, or writing that it works:

```bash
infra/smoke-test.sh      # 28 checks: every public endpoint, every realm and site
infra/journey-test.py    # 18 checks: the reader's journey, at every publisher
infra/logout-test.py     # 19 checks: both sign-out scopes actually differ
infra/totp-test.py       # 14 checks: two-factor really challenges, every realm
infra/local-reader-test.py  # 9 checks: the publisher's own readers are never gated

A test must never select its inputs by the property it is testing. `journey-test`
once asked for priced articles and then checked they were priced, and passed for
weeks while 9,770 of 9,782 articles were free. It also had one home base written
into it while the other could not sign anybody in. Both suites now sweep every
publisher and every home base from the live registry.
```

## Publishers provision themselves

A publisher installs the plugin and activates it; that is their whole job. The
distributable carries **no credentials** — it is a public download at
`dashboard.itega.org/plugin/` — so the plugin fetches its own, proving it
controls the domain by serving a nonce at `/.well-known/newshare-challenge`
which the discovery service then fetches over HTTPS. ACME's HTTP-01 challenge.

ITEGA registers the domains first; that registration **is** the certification
step. See `docs/publisher-onboarding.md`.

Two rules that came from real failures:

- **A key may only file events under its own Publishing Member ID.** `pubMbrId`
  arrives in the request body, so with one shared key any holder could file
  settlement-affecting reads as any publisher.
- **Mount the provisioning *directory*, not the file.** Renaming onto a
  bind-mounted file is renaming onto a mount point; the kernel answers EBUSY,
  and it fails *after* verification succeeds, so it looks like the wrong bug.

Network readers get the **`newshare_guest`** role ("ITEGA Guest"), holding only
`read` — never `subscriber`, which is the publisher's own and which plugins
routinely add capabilities to.

**Anything the agent will say about a reader requires that reader's own session
token.** `GET/PUT /agent/reader/{id}/limit` and `/history` verify the exchange's
`sessionToken` against its published keys and match the `networkUserId` claim
against the path; `/agent/confirm` takes a single-use nonce rather than an
identifier. Without this any publisher could ask a home base where else its
reader goes — every publisher stores its readers' identifiers in `wp_usermeta` —
which is the one join the architecture exists to prevent. Issue #62; the reader's
own page is `/agent/settings`, which holds no privilege of its own.

**A reader has three limits, and any of them asks rather than refuses.** Per
story, per period, and per publication — the last one being how a reader says
"never ask me about my own paper", stored as an explicit null because absent
means "use my general figure". All are measured against **retail**, so they
cannot live at the publisher, which is never told that number. The period tally
is kept on the reader's Keycloak account, not in the agent: a cap that resets
when a container restarts is a suggestion. Spend is recorded *after*
authorisation, so nobody is charged for an article they were not given. Issues
#29, #58; the reader sets them at `/agent/settings`.

**A reader's spending limit is measured against retail, and lives at their home
base.** `src/asp-agent/thresholds.py` holds it as a Keycloak user attribute; a
quote above it returns decision **`confirm`** with a `confirmUrl`, and the reader
approves on their *home base's* page — the publisher cannot show that screen
because it is never told the retail price. Approval is narrow on purpose: this
reader, this article, this price, ten minutes. A reader with no limit is
completely unaffected, and an unreadable limit is treated as no limit rather than
zero, so a directory outage cannot become a network-wide refusal. Issue #29;
there is still no interface for a reader to set one (#58).

**The Retail Agent holds the reader directory, and refuses to use it unproven.**
`src/asp-agent/pairwise.py` inverts the derivation into `networkUserId` → the
home base's own user, scoped to its own realm — HB001's agent returns 404 for an
identifier HB002 minted, which is checked. `GET /agent/reader/{id}/history`
assembles a reader's cross-publisher history there, never at the ALS: doing it
centrally would mean the exchange learning the mapping, which is the one thing
the design exists to prevent. It answers only once live quote traffic has
confirmed the arithmetic twice (`/agent/directory-status`), because an empty
history and a broken derivation are indistinguishable from outside. Keycloak
admin credentials are the wrong grant and are what exists; a service account with
`view-users` and `view-clients` is required before a pilot. Issues #53, #28.

**Every client that sees a reader gets a pairwise mapper, including the
dashboard.** It did not, so `sub` fell through to the reader's actual home base
user id and the exchange held the seed value for every pairwise identifier that
reader has. No join was possible without the salts, but as Gigi put it: privacy
should come from what a party *cannot* know, not from its lacking one ingredient
to exploit what it holds. Fixed in `publisher-c` and `newshare`; `wesmc` has no
dashboard client at all (#60). Issue #56.

**Only the home base can join a reader's pairwise identifiers, and it can.**
Each publisher is a Keycloak client in the home base's realm with its own
`pairwiseSubAlgorithmSalt`, and the identifier is
`UUID.nameUUIDFromBytes(SHA256(sector + localSub + salt))` — hence the version-3
UUIDs. **`sector` is the host of the redirect URI**, since no
`sectorIdentifierUri` is configured, so every publisher shares a sector and the
salt is what separates them; changing a redirect URI would silently re-issue
every reader a new identity. `infra/ppid-derivation-test.py` reconstructs a real
reader's identifiers and checks them against what two publisher sites recorded
independently — run it before trusting anything built on the derivation, because
a wrong join is silent and shows one reader another's history. Issue #53, which
is the shared prerequisite for #28 and #29.

**A client secret belongs to one home base, not to the network.** A client of a
given id exists in every home base's realm and each issues its own credentials;
`PublisherEntry.secret_for(home_base_id)` resolves it and logs loudly when
falling back to a shared value. Issue #23.

**A site that loses its credentials gets them back by itself.** They live in
WordPress options, so an update cannot lose them, but a database restore or a
migration can — and the resulting failure is invisible: the meter counts, the
gate closes, readers are charged, and settlement pays the publisher nothing.
`Newshare_Provisioning::heal()` re-certifies (scheduled, rate-limited to once an
hour) and `verify()` asks `GET /log/whoami` daily whether the key still works.
**One 403 there is a race, not a revocation** — the discovery service writes the
key store and the logging service reads it, and they are not the same instant;
the first version of this deleted good keys in a loop. Two refusals an hour
apart are believed. Issues #50, #52.

**A refusal and a failure to ask are different events, and the reader must be
told which happened.** `Newshare_Pricing` returns `decline` when the home base
refused and `unavailable` when it could not be reached; `payment-declined.php`
and `payment-unavailable.php` say so separately. Collapsing them attributes our
outages to a third party and sends the reader to ask about a decision nobody
made. Link a reader to `account_url` from the registry — never `oidc_issuer`,
which is infrastructure and not a destination. Issue #45, #46.

**The gate names the publisher's price, never the reader's.** `pageClass` is
what the publication is owed; the reader's bill is `pageClass * markupRatio`,
and the publisher's own site is deliberately never told the markup — so the gate
cannot state a retail figure and must not imply that it has. It also says what
the button does, because for a reader whose entitlement does not cover the
article, continuing authorizes a purchase at a price they have not yet seen. A
home base may be a library or a cooperative, not only a newspaper, and
continuing never reveals the reader: the publisher gets a pairwise opaque
identifier before and after. Issue #43, found by Jason Velazquez's AI reviewer
reading the repository and spotting that the comment above the string
contradicted the string.

**A publisher's own signed-in readers are never gated, metered or quoted.**
Subscribers, members, monthly contributors and staff read everything on their
own newspaper's site; the network is for visitors from elsewhere, and a plugin
that came between a publisher and the people already paying them would be worse
than no plugin. The check reads the role as well as the link meta, so an account
whose meta is lost fails towards the gate rather than into the publisher's
audience. Issue #41, and Jason Velazquez's condition for installing it.

**The realm files must describe what is running, and `infra/realm-config-test.py`
checks that they do.** They declared two clients while four ran; `pub-c` and
`dashboard` had been added by hand and never written back, which is the whole of
#60 — wesmc simply missed the by-hand step. The check also enforces #56's rule
(every client that sees a reader gets a pairwise subject) and that unmanaged
attributes are enabled, without which a reader's threshold cannot be stored.
**Secrets and salts never go in this repository** — it is public, and a committed
salt lets anyone who learns a reader's local subject compute their identifier at
that publisher. They live in `infra/vps*/secrets/` on the hosts, gitignored, and
want backing up: losing one costs no reader and no settlement, but every
publisher would meet every reader as a stranger. Issues #60, #61.

**Deploy the services, then prove it.** VPS 2 is a git checkout at
`/opt/newshare`; ship with `git pull` there and
`docker compose up -d --build <service>`, and note that code is baked into the
images while `registry.json` is bind-mounted — so a data change needs no rebuild
and a code change does. `smoke-test.sh` now compares the deployed commit against
`origin/main`, because a stale deploy is indistinguishable from a healthy one:
#47 removed a phantom publisher, the commit went green, and the live registry
went on serving it. Issue #51.

**Update the demonstration sites the way a publisher does**, with
`infra/update-demo-sites.sh` — WordPress's own updater against the public
manifest. Shipping to our own sites by rsync means the mechanism every real
publisher depends on is exercised by nobody until it fails at their end; that is
how #49 hid, where `wp plugin update` could never see an ITEGA release at all.
`deploy-publisher-plugin.sh` remains the way back when an update goes wrong, and
the bootstrap when installed code cannot yet update itself.

**Publish the plugin with `infra/publish-plugin.sh` after every change.** It
lints, packages, writes the update manifest, uploads, and then checks what is
actually served against what was built. Installed copies learn about the new
version through WordPress's own update machinery. Greylock Glass ran a build
one hour stale with no way to know, which is what this prevents.

Deploy the publisher plugin only with `infra/deploy-publisher-plugin.sh <site>`
(or `all`). It lints locally, ships the plugin as a unit, checks real pages
afterwards and rolls back if the site stops answering. Copying single files with
`scp` is what took barharbor.info down; there is no longer a supported way to do
it. `NEWSHARE_DEPLOY_FORCE_FAIL=1` rehearses the rollback against a healthy
site.

These exist because the sign-in path was broken for weeks and nobody knew. When
it was finally walked start to finish it turned up **seven separate faults**, any
one of which stopped a reader dead — a missing PKCE challenge, a GET-only
callback the ALS posted to, a parameter named two different things on the two
sides, a wrong authorize path, a scope no home base defines, an
`OpenSSLAsymmetricKey` cached into a transient, and a token signed without a
`kid`. Five more were found elsewhere, including publishers never filing the
purchases they were owed for.

Every one of them looked healthy from the hop before it. Checking that a service
returns 200 proves almost nothing about whether a person can get through it, so:

- **Assert on the result, not the redirect.** A 302 towards a login page is not
  a login.
- **Walk the whole path** as a reader does, from the article to the session, not
  from the API inwards.
- **Log defects as GitHub issues** with cause, fix and verification, then close
  them with what proved the fix. **Every fix and every feature request gets an
  issue, including ones already solved** — the tracker is the project's log of
  what was done and why, and a change that only exists as a commit message is
  not findable by anyone who was not there. `gh issue list --state all` is the
  record.

**The recurring failure in this project is a check that cannot observe what it
claims to.** Not a wrong threshold — a quantity that could not have revealed the
fault whatever its value. `journey-test` selecting articles by the property under
test; a frame check reading file sizes when every frame was the same picture; a
mix check reading total loudness to find a bed 18 dB down. Each passed happily
while the thing it named was broken. Before trusting a check, ask what value it
would print if the feature were entirely absent — and if the answer is "the same
one", the check is decorative.

The ALS base URL is the **host only** — the flow lives under `/auth/`. Two
separate codebases got this wrong independently.

**This repository is public** — Bill's Editor & Publisher column links to it directly.
Correspondence and source documents belong in `reference/`, never in a commit.

## Important Constraints

- The pilot targets **3-5 independent Missouri newspapers** via MPA
- Budget is **$400,000 over 18 months**
- Infrastructure budget is **$300-$500/month** for a single cloud VM
- The pilot is a **proof-of-concept**, not a scale deployment
- Success = **50+ real users** complete cross-publisher authentication
- Phase 2 (UDEX — User Data Exchange) is explicitly deferred; do not build it now

## Evolution Path: Decentralized Identity

The current OIDC-based architecture is a pragmatic starting point. Peer review (Drummond Reed, Feb 2026)
identified a future migration path to **Verifiable Trust Networks (VTNs)** based on W3C DIDs, Verifiable
Credentials, and Trust Over IP (ToIP) standards. Key points:

- The four-party model maps one-to-one onto ToIP's VTN concept (ITEGA → VTN Governance, Home Base → Credential Issuer, Publisher → Verifier, ALS → Trust Registry)
- Current architecture already includes bridge decisions: PPID, no central DB, W3C VCs in protocol stack, no cookies, JWT tokens (same format as JWT-VC)
- Phase 1 = OIDC pilot (ship now). Phase 2+ = migrate to DID/VC as ecosystem matures.
- See `docs/peer-review-synthesis.md` for full analysis and migration roadmap.
- The **First Person Cooperative** and **Content Authenticity Initiative** (Adobe/C2PA) are potential partners for a media-industry VTN.

## Source Documents

The definitive technical reference is `claude-itega-newshare-tech-spec-02-22-26b-1110pest.pdf`
in `docs/source-pdfs/`. When in doubt about architecture, protocol choices, or field names,
refer to that document. The funder brief and chat transcript provide additional business context.
