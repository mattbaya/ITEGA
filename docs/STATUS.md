# Project Status and Plan Forward

*Living handoff document. Anyone — or any session — picking this up cold should be
able to read this file and continue without reconstructing context.*

**Last updated:** 2026-08-11 — both servers live, demo running in production
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
| `src/wordpress-plugin/` | Negotiation and AI-agent 402 flow wired in; not yet run against live WordPress. |
| `src/dashboard/` | **Live** at `dashboard.itega.org/demo`, driving production services. |
| `infra/vps1`, `infra/vps2` | **Deployed and running.** Apache vhosts, TLS, both realms imported. |

**Verified in production** (Aug 11): home-base resolution across hosts, all three
negotiation outcomes, the AI agent handshake, the dashboard walkthrough driving live
services, and two home bases returning different retail prices for one wholesale price.

**Still unverified:** anything involving WordPress. The plugin has never run against a
live site, so the reader's journey through an actual publisher — gate, negotiation,
purchase notice — and the AI agent's 402 exchange against a real page remain untested.
That is the largest remaining risk.

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

### 1. Publisher sites — set up, plugin not yet installed

`barharbor.info` (Publisher A) and `northberkshire.org` (Publisher B) are
configured and seeded with demo articles priced for the negotiation. Bar Harbor
has been restyled and moved to its Divi child theme. Full detail, and the
WordPress-specific traps met along the way, in `docs/publisher-sites.md`.

Two sites is enough: the cross-publisher leg needs a second publisher, not a
third. Publisher C is the home base, a Keycloak realm, not a website.

**What remains is the last genuinely untested part of the system:** installing
the plugin and walking a reader through the gate, the negotiation and the
purchase notice on a real site. Pre-configured packages are built by
`infra/build-publisher-plugin.sh`.

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
