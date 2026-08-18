# Project Status and Plan Forward

## 2026-08-18 — publishers provision themselves, and Greylock is registered

**A publisher now installs the plugin and activates it. That is their whole
job.** No member ID typed in, no API key pasted into a form. The distributable
carries no credentials — it is a public download at
`dashboard.itega.org/plugin/` — so the plugin fetches its own, proving it
controls the domain by serving a nonce the discovery service then fetches back
over HTTPS. ACME's HTTP-01 challenge. See `docs/publisher-onboarding.md`.

**greylockglass.com and greylockguardian.com are registered**, so Jason
Velazquez can skip registration entirely. He is hosting this as a favour, on the
condition it never affects his ordinary readers, and demo mode is what keeps
that promise: with it on and no key in the URL, nothing reader-facing happens at
all.

**A shared API key let any holder file settlement records as any publisher.**
`pubMbrId` arrives in the request body, so with one key across the network,
whoever held it could credit themselves for reads that never happened, or load a
competitor with traffic they never had. Keys are per publisher now, and a key
may only file events under its own member ID. Verified live: wesmc's key files
as itself (202), as Bar Harbor (403), an invented key (403).

**Network readers get their own role**, `newshare_guest` ("ITEGA Guest"),
holding only `read`. Never `subscriber` — that is the publisher's own role, and
plugins routinely add capabilities to it, so a network reader would inherit
access nobody decided to grant. It also makes these accounts a visible group in
a users list, which matters on a site hosted as a favour. `uninstall.php`
removes the settings and the role but not the accounts; those may have comments
attached and belong to the site owner.

### Verified by wiping a live site

wesmc.org had its credentials deleted and re-certified from scratch, as a fresh
install would. One call, correct member ID, per-publisher key, demonstration
key, and 18/18 journey checks afterwards. That also exercised the plugin's own
challenge-serving, which an earlier static-file test had not.

### Two failures worth not repeating

- **`os.replace` onto a bind-mounted *file* returns EBUSY.** Docker makes the
  file a mount point, so the atomic write protecting the store failed — *after*
  the domain had verified, which made it look like a verification bug. Mount the
  directory.
- **FastAPI exports its own `Path`**, which shadowed `pathlib.Path` in
  als-logging. The container started, `/healthz` answered 200, and every
  authenticated request returned 500 including ones that should have been a
  clean 403.

Both are the recurring shape: a check that cannot observe what it claims to. A
health endpoint answering 200 while every real request fails is not a health
check.

### Also

Films re-rendered twice: "eye-TAY-ga" as a speech-only respelling (the slides
still read ITEGA), and the baker analogy moved from pounds to dollars, both at
Bill's request. 51 demonstration accounts exist for 17 people across all three
home bases.

## 2026-08-18 (evening) — Bill calls a freeze, and settles the reader dashboard

**No more changes before Aug 25 other than fixing something that breaks.** Bill's
call, and a correct one: nothing has been promised to anyone, and polish four
days out risks more than it gains. Tests, docs and issue-writing continue, since
they change nothing that runs on the day.

Two things were settled rather than built.

**The reader's cross-publisher history (#28) has an answer, and Bill found it.**
He proposed that the home base assemble it from logging-service data. That is
right, and it costs the architecture nothing: the home base mints the pairwise
identifier for its user at each publisher, so it alone holds the map from one
person to their several PPIDs, and it can query the log once per PPID and join
the results. No other party can, and no collusion between publishers reproduces
it. Built at the home base, never at the ALS — assembling it centrally would
require the ALS to learn the mapping, which is the one thing the design exists to
prevent. Where the reader has been is free; what they were charged lives in the
home base's own billing.

**Publishers have an API but no dashboard (#44).** The party being asked to
install a plugin and trust a settlement figure cannot see their own weekly totals
without writing a curl command. Aggregates only when it is built — never retail
prices or markup.

**barharbor.info's public notices are now free.** Twenty-one road closures,
meeting listings and hearing notices from 2025 and 2026. Public notices outside
the paywall, reporting behind it. The archive stays priced at any age; the meter
still closes sixty articles deep on all three sites.

## 2026-08-18 — Greylock Glass installed it, and read the paywall properly

Jason Velazquez put the plugin on greylockglass.com — the first install by
anyone outside this project — and showed the gate to an AI reviewer, which read
the repository and found that the screen contradicted the code beneath it.

The gate said "This story costs 5¢". Five cents is `pageClass`, the wholesale
price. The reader pays `pageClass * markupRatio`, which across our three home
bases is 5.5¢, 6.25¢ or 7¢. The comment directly above the string said exactly
that, and the string said otherwise. The retail figure appeared only *after* the
purchase, in the notice — so a reader met the wrong number before deciding and
the right one afterwards.

Four more in the same panel: an "included" promise the pricing code may refuse,
"your own newspaper" when a home base may be a library or a cooperative, a
privacy sentence implying that continuing reveals the reader, and a button that
reads as a login while also authorizing a purchase at an unseen price.

All fixed in **0.2.5**, deployed to the three sites and published. Issue #43.

Also this day: the publisher's own signed-in readers are exempt from the gate
entirely (#41), the demo-mode checkbox is gone and a one-way door back exists
for sites stranded by its removal (#38, #42), and the plugin updates itself
through WordPress (#37).

## 2026-08-17 — two films, and a renderer that lied three ways

The 120-slide explainer is now narrated video: a **12-minute cut** for
circulation and a **28-minute full version**, both served with the slides from
the unlisted preview. Both are built from one set of frames and one set of
speech, so the cut cannot drift from the full version; re-cutting costs only the
six-minute assembly. `scratchpad/deck1/make_video.py`.

Copland's *Fanfare for the Common Man* loops underneath — applause cut from
every pass, Emerson Lake and Palmer held back to the final loop. The bed spaces
its own repeats so a brass entry lands on the turn in the argument, and it
re-scored itself for the shorter film without being told: seven passes became
three, and the swell moved from 8m18s to 4m22s to meet the turn's new position.

**Three renderer faults, each of which produced confident, wrong output:**

- **Every frame was slide one.** The per-slide page was sliced at the nav rail,
  which is appended *after* the slides — so "head" was the entire deck and each
  screenshot caught the top of it. 120 files, all plausible, all identical.
- **Chrome cannot screenshot any more.** Chrome 151 removed the old headless
  mode; `--headless --screenshot` starts the full browser and hangs. A one-line
  page never returned in three minutes. `chrome-headless-shell` does all 120
  frames in 91 seconds.
- **Five slides shared ids.** The Visa-parallel set inserted mid-deck was
  numbered straight on from its neighbour and collided with the journey slides.
  Narration is cached per id, so five slides would have spoken another slide's
  script — fluently, over the wrong pictures.

**The lesson is the same one this project keeps relearning**, and it is now
written into `CLAUDE.md`: the checks that failed here were not mis-tuned, they
were measuring quantities that could not have revealed the fault. File sizes
cannot detect identical frames. Total mix loudness cannot detect a music bed
18 dB below the narration. Before trusting a check, ask what it would print if
the feature were entirely missing.

`verify.py` now rebuilds the bed and subtracts it from the finished film — if
the bed is present and aligned, it cancels — and reads its timings from a
sidecar the assembly writes, so it cannot verify one cut against another's
numbers.

Slides 12 and 14 carry photographs rather than emoji: display advertising in a
1907 newspaper (public domain) and a brick wall going up (CC BY-SA). Gemini
image generation was attempted first and is unavailable on this key — every
image model returns 429 on the free tier and the Imagen endpoints are closed to
new users. It needs billing enabled on the project.

### The fourteen articles, and a correction worth keeping

Fourteen wesmc.org articles were unpublished on the assumption that a run of
crime headlines naming real Boston venues had to be invented. **Every one was
real** — the Acton case, the South Station stabbing, the TD Garden death, the
Stevie Nicks reschedule, all with mainstream coverage. They are restored, and
the bodies check out too: events summarised, claims attributed, no fabricated
quotes. wesmc.org is back to 122 published articles, which is what the deck and
`publisher-sites.md` already said.

The mistake was pattern-matching a headline shape instead of spending ninety
seconds on a search. Where content looks wrong, verify before removing, and
prefer drafting to deleting.

## 2026-08-17 — Bill tested it, and found what our tests could not

Bill Densmore spent an evening clicking, and every one of his reports was real.
The pattern is worth naming: **each fault was invisible to a suite that
exercised the path it was built around.**

- **Almost nothing was for sale** (#18). Both sites carry their real archives,
  and exactly four articles on each had a price. The test asked the site for
  priced articles, then checked those articles were priced — it chose its
  inputs by the property under test. All 9,823 articles now carry a price, and
  the suite picks articles the way a reader does, including from deep in the
  archive.
- **The second home base could never sign anyone in** (#22). Different client
  secrets per realm against one secret at the exchange: 401 on every exchange
  since the day it was created, while every test passed, because the suite had
  one home base written into it. It now sweeps every certified home base.
- **The dashboard looped back to the login page** (#19), then **greeted him as
  "Alex Morgan" with an invented reading history** (#21).
- **The first click on the network login did nothing** (#24) — a hand-off page
  with no visible content while WordPress bootstrapped behind it.
- **"Create an account" led to a login form** (#25), because a bare Keycloak
  registration URL silently degrades to sign-in.

### What changed as a result

Three publishers and three home bases, and each organisation now does both jobs:
Bar Harbor, North Berkshire and West End Sentinel are each a publisher *and* a
home base, so nobody meets an organisation that appears nowhere else (#27).
wesmc.org is the third site, running the same plugin.

Readers are named from their pairwise identifier — Reader 948AFC — so a site
with six of them no longer greets all six identically (#26).

Eleven demonstration accounts exist for named colleagues, spread across the
three home bases so two people reading the same article are billed differently
while the publisher is paid the same. Credentials live outside the repository.

### One thing that is not fixed, and needs a decision

**The reader's dashboard cannot show cross-publisher activity** (#28), and no
amount of fixing the query will change that. The dashboard is a client, so it
holds a fourth pairwise identifier that appears on none of the reader's reading.
Only the home base can link them — and an exchange that could would be proof the
pairwise identifiers were not working. Three options are in the issue; it wants
a decision rather than a patch.

## 2026-08-16 — the sign-in path was broken, and now is not

The reader's authenticated journey had never been walked end to end. Walking it
found **seven separate faults** between a reader and a signed-in session, any one
of which stopped the journey dead, plus five more elsewhere. All twelve are in
the issue tracker with cause, fix and verification: github.com/mattbaya/ITEGA/issues

The ones worth remembering:

- **No PKCE challenge** (#1). Keycloak requires it; the ALS was not sending one,
  so every home base refused every sign-in and the reader saw a raw JSON error.
- **Publishers never filed their own purchases** (#12). Logging ran only when the
  reader's *tier* granted access, which is the one case a purchase is not. A
  publisher could sell all day and settlement would credit it nothing.
- **A returning reader could be locked out permanently** (#17). Lookup is by user
  meta; if that goes missing the code tries to create a duplicate account, the
  login collides, and every future attempt 500s. Now self-healing.
- **Monitoring would never have told anyone anything** (#16). Zero alert rules,
  SMTP disabled. Sixteen rules now exist and the disk rule fired on dev-svaha
  within a minute. Delivery is still unconfigured.

Five test suites now guard this and should be run before showing anyone anything:

    infra/smoke-test.sh        28 checks, every public surface
    infra/journey-test.py      18 checks, the reader's journey end to end
    infra/logout-test.py       19 checks, both sign-out scopes, and that they differ
    infra/totp-test.py         14 checks, two-factor really challenges, both realms
    infra/local-reader-test.py  9 checks, the publisher's own readers are never gated

Verified working: cross-publisher recognition with distinct pairwise identifiers,
all three negotiation outcomes in the real reader flow, the wholesale/retail
split, the AI agent handshake refused and paid, publisher logging at the agreed
price, settlement balancing at 0.5500, the 14-step walkthrough against live
services, RSL metadata, 30-minute tokens, and signature validation refusing a
tampered networkGroupId.

**Sign-out now asks how far to go** (#15). Two options, because they are two
different acts: leaving this publisher, or leaving the network and the home base
with it. The second is the one that matters on a shared machine, and it says so.
The real bug was not that WordPress stopped at WordPress — it was that the ALS
kept a usable token, so a reader who logged out and clicked a gated article was
signed straight back in without a login screen. Three sessions end now, held by
three parties.

**Two-factor is available at both home bases**, opt-in from the account console
at `auth.itega.org/realms/<realm>/account/`. TOTP, so any authenticator app
works. Deliberately not forced: making it a default required action would put an
enrolment screen in front of every demo login, including Bill's. Flipping it to
mandatory is one attribute per realm when that is wanted. Email one-time codes
are **not** available — Keycloak has no built-in email OTP, and it would need a
custom SPI plus an SMTP server the deployment does not have.

**Publisher plugin deploys are now a script** (#11), whole-plugin-only, with a
local lint, real page checks afterwards and automatic rollback. The two sites had
already drifted apart — 400K against 436K — from earlier file-by-file copying.

**Still open:** settlement moves no real money; alert delivery unconfigured (a
Beszel configuration task, not ours); and dev.svaha.com is at 93% disk.

A note on this document: it briefly named a live client secret. Never write a
credential's value here, even to flag it as weak -- this repository is public,
and saying which string a secret is set to is worse than the weak secret itself.
Name the client and say "needs rotating".


*Living handoff document. Anyone — or any session — picking this up cold should be
able to read this file and continue without reconstructing context.*

**Last updated:** 2026-08-18 — change freeze until the 25th; #28 settled by Bill
**Deadline:** Aug 25, 2026 — RJI/ITEGA roundtable, 2 p.m. EDT

---

## Where to look first

| For | Read |
|---|---|
| What Bill wants demonstrated | `reference/ITEGA-RJI-demo-script-08-07-26.md` *(gitignored — local only)* |
| Script vs. code, and Bill's answers | `docs/demo-script-gap-analysis.md` |
| Host sizing and layout | `docs/server-specs.md` |
| How to build the servers | `docs/vps-provisioning-plan.md` |
| Architecture rules that must not be broken | `CLAUDE.md` |
| Peer review context (Reed, Marti) | `docs/peer-review-synthesis.md` |

**Bill revises the demo script.** Check `reference/` for the newest
`ITEGA-RJI-demo-script-*.md` before building anything; he has already replaced one
version, and the 08-07 revision materially changed the pricing section.

---

## Rules that must survive any refactor

These are not preferences. Breaking one of them breaks the argument the demo exists
to make.

1. **`pageClass` is wholesale; `pageClass × markupRatio` is retail.** Only wholesale
   settles through the ALS. The markup is the home base's margin.
2. **Never disclose `markupRatio` or retail totals to publishers.** The Rights Owner
   is not entitled to the Retail Agent's margin.
3. **Identifiers are pairwise.** A reader is a different opaque person at every
   publisher, and only their home base can mint that identifier. Never let the ALS
   generate one, and never hand the same one to two publishers.
4. **The Retail Agent runs on the home base's host,** never on the ITEGA host. It
   holds the markup and decides purchases; ITEGA may see neither.
5. **Publishers are named by letter (A, B, C).** The script's "Publisher 1/2/3" are
   the same parties; letters win everywhere.
6. **No auth cookies between parties.** The one cookie in the system is first-party on
   the Authenticator's own domain and holds only an opaque handle.
7. **The repo is public.** Correspondence and source documents live in `reference/`,
   which is gitignored. Bill's Editor & Publisher column links to the repo directly.

---

## What is built and verified

| Component | State |
|---|---|
| `src/network-discovery/` | Working. Registry, home-base resolution, WebFinger. |
| `src/als-auth/` | Working. Multi-home-base routing, chooser, session cache, AI agent handshake. |
| `src/asp-agent/` | Working. Accept / negotiate / decline, markup withheld. |
| `src/als-logging/` | Working. Per-filer event records. |
| `src/als-settlement/` | Working. Wholesale settlement, corrected. |
| `src/wordpress-plugin/` | **Live on all three publisher sites.** Gate, authenticated path, negotiation, purchase notice and both sign-out scopes all verified against the live sites. |
| `src/dashboard/` | **Live** at `dashboard.itega.org/demo`, driving production services. |
| `infra/vps1`, `infra/vps2` | **Deployed and running.** Apache vhosts, TLS, both realms imported. |

**Verified in production** (Aug 11): home-base resolution across hosts, all three
negotiation outcomes, the AI agent handshake, the dashboard walkthrough driving live
services, and two home bases returning different retail prices for one wholesale price.

**Verified since** (Aug 16): the whole WordPress leg, which was the largest remaining
risk and is now the best-tested part of the system. The reader's journey through a real
publisher — gate, sign-in, negotiation, purchase notice, crossing to the second site —
and the AI agent's 402 exchange, grant, and continued crawling against real pages. Both
sign-out scopes and TOTP enrolment are covered by their own suites.

Walking it found seven faults between a reader and a session, plus five more elsewhere.
None were visible from the hop before.

### Bugs found and fixed (worth knowing about)

- **Settlement paid publishers the retail price**, handing the home base's margin to
  the publisher and inverting the business model.
- **The WordPress plugin could not load at all** — `class-newshare-oidc.php` declared
  an illegal `object|WP_Error` return type, so the file never parsed.
- **Every negotiated purchase would have been billed twice** once both parties began
  filing log reports, until events recorded which party filed them.

---

## Plan forward

Every build task from Bill's Aug 7 script and his Aug 8 replies is done. What
remains is deployment and rehearsal, not development.

### 0. Deployed and working

Both hosts are live. See `docs/vps-setup-record.md` for how they were built and
`docs/monitoring.md` for the monitoring state.

| Service | Status |
|---|---|
| Keycloak, two home-base realms | Live, imported from version control |
| Both Retail Agents | Live, markups 1.1 and 1.4 |
| Authenticator, Logger, Network Discovery | Live |
| Dashboard and the `/demo` walkthrough | Live, driving the production services |
| TLS on all six hostnames | Live, auto-renewing |

**Verified in production:** the network resolves home bases across hosts, all
three negotiation outcomes work, the AI agent handshake works, and — the check
worth repeating — the same $0.05 article bills one reader $0.055 and another
$0.07 because their home bases apply different markups. That single result
exercises the registry, both agents, the proxy layer and the pricing model.

### 1. Publisher sites — live, plugin deployed and exercised

`barharbor.info` (Publisher A) and `northberkshire.org` (Publisher B) are
configured and seeded with demo articles priced for the negotiation. Bar Harbor
has been restyled and moved to its Divi child theme. Full detail, and the
WordPress-specific traps met along the way, in `docs/publisher-sites.md`.

Two sites is enough: the cross-publisher leg needs a second publisher, not a
third. Publisher C is the home base, a Keycloak realm, not a website.

**The plugin is installed and active on both sites**, configured entirely on
activation with nothing typed. The access gate is verified against the live
site: three free reads, then the gate closes on the fourth and the body is
withheld.

The **authenticated** path is verified too — signing in through a home base, the
price negotiation, the purchase notice, and crossing to the second publisher with a
different pairwise identifier. Deploy only with
`infra/deploy-publisher-plugin.sh <site>`; copying single files is what took
barharbor.info down.

`greylockglass.com` — a real operating news site — may join later. That would be
a far stronger demonstration than three sites we control, and is worth attempting
only once the flow is proven on these.

### 2. Monitoring — DONE
Four hosts reporting to `monitor.itega.org`: both Hetzner servers plus the two
existing estate machines. Agents dial out over 443, so no inbound port is open
on any of them. See `docs/monitoring.md`.

Two follow-ups: the hub login was shared in a transcript and should be rotated,
and `restic` is installed but not yet scheduled.

### 3. Replace every placeholder
Realm client secrets, pairwise salts, demo passwords, the AI agent API keys in
`src/als-auth/data/ai-agents.json`, and `PUBLISHERS_CONFIG`. All are marked
REPLACE-ME and all are currently in a public repository.

### 4. Redaction and git history — CLOSED

Don Marti's and Rick Lerner's addresses were redacted from the tracked PDFs and
history was rewritten so no commit yields them. Bill's own details were left as
they are.

**Decided (Matt, Aug 11): no further action.** The exposed material was contact
details, not anything sensitive, so the residual traces are not worth chasing —
neither GitHub's retention of the pre-rewrite commits by SHA, nor confirming the
decision with Bill. Recorded here so it is not repeatedly re-raised.

For anyone reading this later: the original commits remain fetchable from GitHub
by direct SHA until GitHub is asked to collect them, and roughly 53 clones
predate the rewrite. That was known and accepted, not overlooked.

### 5. Rehearse
Bill presents this. The demo is presenter-paced by design, but he has not seen it.

## Open with Bill

- **Drummond's VTN framing** ("what you could create is a verifiable trust network for
  news") is worth adopting as positioning even while deferring the technology. Costs
  nothing; `docs/peer-review-synthesis.md` already has the mapping.
- **Session token lifetime** is 30 minutes, matching Bill's suggestion. Answered but
  worth confirming he saw it.

---

## Working agreements

- Build it **really working**; simulation is the fallback, not the goal.
- Push to GitHub as work lands, so the public engineering picture stays current.
- Never commit `reference/`.
- Bill overrode the advice to discard the AI-generated codebase ("a bird in the hand").
  Build on `src/`; that decision is settled.
