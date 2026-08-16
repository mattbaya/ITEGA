# Project Status and Plan Forward

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

Four test suites now guard this and should be run before showing anyone anything:

    infra/smoke-test.sh     28 checks, every public surface
    infra/journey-test.py   12 checks, the reader's journey end to end
    infra/logout-test.py    19 checks, both sign-out scopes, and that they differ
    infra/totp-test.py      14 checks, two-factor really challenges, both realms

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

**Last updated:** 2026-08-16 — reader's journey verified end to end; sign-out scopes and TOTP added
**Deadline:** Aug 25, 2026 — RJI/ITEGA roundtable, 2 p.m. EDT

---

## Where to look first

| For | Read |
|---|---|
| What Bill wants demonstrated | `reference/ITEGA-RJI-demo-script-08-07-26 document.md` *(gitignored — local only)* |
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
| `src/wordpress-plugin/` | **Live on both publisher sites.** Gate, authenticated path, negotiation, purchase notice and both sign-out scopes all verified against the live sites. |
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
a far stronger demonstration than two sites we control, and is worth attempting
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

- **Calendar invite** for the Aug 25 webinar to `drummond.reed@gmail.com` — he asked,
  and it is easy to lose in a long thread.
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
