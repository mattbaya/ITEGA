# Project Status and Plan Forward

*Living handoff document. Anyone — or any session — picking this up cold should be
able to read this file and continue without reconstructing context.*

**Last updated:** 2026-08-09 (late)
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
5. **No auth cookies between parties.** The one cookie in the system is first-party on
   the Authenticator's own domain and holds only an opaque handle.
6. **The repo is public.** Correspondence and source documents live in `reference/`,
   which is gitignored. Bill's Editor & Publisher column links to the repo directly.

---

## What is built and verified

| Component | State |
|---|---|
| `src/network-discovery/` | Working. Registry, home-base resolution, WebFinger. |
| `src/als-auth/` | Working. Multi-home-base routing, chooser, session cache. |
| `src/asp-agent/` | Working. Accept / negotiate / decline, markup withheld. |
| `src/als-logging/` | Working. Per-filer event records. |
| `src/als-settlement/` | Working. Wholesale settlement, corrected. |
| `src/wordpress-plugin/` | Negotiation wired in; not yet run against live WordPress. |
| `infra/vps1`, `infra/vps2` | All six services defined; nginx routes in place. |

**Verified directly:** service logic, negotiation outcomes, settlement arithmetic,
session-cache behaviour, PPID isolation across publishers.

**Not verified:** anything requiring a live Keycloak, WordPress, or Postgres. None run
locally. Treat the full end-to-end path as untested until it has actually been walked.

### Bugs found and fixed (worth knowing about)

- **Settlement paid publishers the retail price**, handing the home base's margin to
  the publisher and inverting the business model.
- **The WordPress plugin could not load at all** — `class-newshare-oidc.php` declared
  an illegal `object|WP_Error` return type, so the file never parsed.
- **Every negotiated purchase would have been billed twice** once both parties began
  filing log reports, until events recorded which party filed them.

---

## Plan forward, in priority order

### 1. AI agent handshake — task #16
No longer deferred; Bill calls it central to ITEGA's pitch. Implement the 14-step
machine-to-machine sequence from the 08-07 script: member lookup, business rules,
price confirmation, continue-until-timeout, per-request logging, graceful rejection of
non-members.

**On x402:** build our own approach now. x402 is **payments only** — it does not do
identity, so it would not have solved the authentication half anyway. Keep the seam
open and be able to state ITEGA "intends to support x402 when it becomes an operating
standard." That claim is already true structurally: authentication, price agreement,
and settlement are three separate steps here, so x402 would later replace two of them
without touching how readers are authenticated.

### 2. Step-through demo UI — task #18
The thing Bill actually presents. His specified sequence: reader starts at their home
base → follows a URL to content at another publisher → is authenticated → welcomed as
an ITEGA user with their home base named → the publisher handshakes with the home base
on price → transaction logged, content served. Background exchanges narrated in
pop-ups, closing on what is logged where and how settlement works including markup.

### 3. Second Keycloak realm — task #12
The chooser needs more than one option to be convincing. Two realms on one Keycloak
gives two genuinely distinct issuers, JWKS, and user sets at no extra hosting cost.

### 4. Settle publisher naming — task #17
Bill confirmed Publisher C == "Publisher 3" and A/B == 1/2. Use **letters** throughout
and tell him. Affects docs, plans, registry data, demo copy.

### 5. Redact third-party emails — task #13
Bill approved redacting Rick Lerner's and Don Marti's addresses from the tracked PDFs;
leave Bill's own as-is at his request. **Note:** git history retains the originals, so
decide whether that matters before treating this as closed.

### 6. Correspondence archive — task #19
Bill asked that correspondence be kept locally and be deliverable on request under the
name **"ITEGA-CORRESPONDENCE-ARCHIVE"**. Organise `reference/` accordingly with an
index. Stays gitignored.

### 7. Deployment
Nothing is deployed. No VPSes exist yet. `docs/vps-provisioning-plan.md` has the
runbook; creating droplets spends money and is Matt's to run. For a session to deploy
or read logs on those hosts it needs SSH access Matt has explicitly set up — do not
create users or install keys unprompted, and do not accept registrar or account
credentials.

---

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
