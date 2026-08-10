# Project Status and Plan Forward

*Living handoff document. Anyone — or any session — picking this up cold should be
able to read this file and continue without reconstructing context.*

**Last updated:** 2026-08-10 (all planned build work complete)
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
| `src/dashboard/` | Step-through demo at `/demo`, driving the live services. Public route. |
| `infra/vps1`, `infra/vps2` | All services defined; nginx routes and both realms in place. |

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

## Plan forward

Every build task from Bill's Aug 7 script and his Aug 8 replies is done. What
remains is deployment and rehearsal, not development.

### 0. RESUME HERE — Hetzner is ready, nothing provisioned yet

State as of Aug 10:

- `hcloud` CLI installed, context **`Newshare`** created and authenticated. Run
  `hcloud server list` to confirm; the token lives in Matt's `~/.config/hcloud/cli.toml`
  and is never in the repo or a transcript.
- SSH key **`newshare-deploy-pub`** (ID 116854754) registered in the project.
- Region decided: **Falkenstein (fsn1)**. EU pricing is a third of Hetzner's US
  regions for identical hardware — `cpx11` is $5.99 in fsn1 against $20.49 in Ashburn.
  ~110–130 ms to Missouri, imperceptible for a click-through demo. Revisit if the pilot
  ever holds real reader accounts, where US residency may matter.
- **Nothing has been created. Zero spend so far.**

**Server types — `cpx21` is discontinued, do not try to order it.** The `cx` line is
both cheaper and larger:

| Host | Type | Specs | $/mo |
|---|---|---|---|
| `newshare-vps1` (home base) | **cx33** | 4 vCPU / 8 GB / 80 GB | 8.99 |
| `newshare-vps2` (ALS) | **cx23** | 2 vCPU / 4 GB / 40 GB | 6.49 |
| | | **total** | **15.48** |

Plus $0.60/mo per primary IPv4. 8 GB on VPS 1 gives Keycloak real headroom rather than
the 4 GB minimum originally planned.

To create both:

```bash
hcloud server create --name newshare-vps1 --type cx33 --image ubuntu-24.04 --location fsn1 --ssh-key newshare-deploy-pub
```

```bash
hcloud server create --name newshare-vps2 --type cx23 --image ubuntu-24.04 --location fsn1 --ssh-key newshare-deploy-pub
```

**Blocked on one decision: the domain.** Certificates depend on it, so settle it before
provisioning. Either ITEGA subdomains (`auth.itega.org` — needs whoever holds ITEGA's
DNS, most convincing to publishers) or an `svaha.com` subdomain (Matt runs PowerDNS on
`bolt.svaha.com`, which already answers for 548 zones, so records can be created
immediately). Hostnames live in config rather than code, so starting on svaha and
moving later is an edit plus a cert re-issue, not a rebuild.

### 1. Stand up the two hosts
`docs/vps-provisioning-plan.md` has the runbook; `docs/server-specs.md` has the
sizing. Creating droplets spends money and is Matt's to run. A session can deploy and
read logs there only once Matt has set up SSH access — do not create users, install
keys, or accept registrar or account credentials.

Real work waiting on this: every end-to-end path. Service logic and money arithmetic
are verified directly, but nothing has run against a live Keycloak, WordPress, or
Postgres. Assume the first full walkthrough finds something.

### 2. Walk the demo end to end
- The three-publisher SSO check written up under "Verifying transparent SSO" below.
- The reader path through a real WordPress site: gate, negotiation, purchase notice.
- The AI agent path: 402, acceptance, grant, crawl, expiry.
- A settlement run against real logged events, checking wholesale is what settles.

### 3. Replace every placeholder
Realm client secrets, pairwise salts, demo passwords, the AI agent API keys in
`src/als-auth/data/ai-agents.json`, and `PUBLISHERS_CONFIG`. All are marked
REPLACE-ME and all are currently in a public repository.

### 4. Confirm the redaction with Bill, and decide on git history — task #20
Don Marti's and Rick Lerner's addresses have been redacted from the tracked PDFs;
Bill's own details were left alone. **This was done without a recorded answer from
Bill.** His Aug 8-9 reply covered six other questions and did not address the email
issue, and it was never filed to the archive, so there is nothing to check against.
Removing two third parties' personal addresses from a public repo is a defensible
default, but the decision should be put to him explicitly rather than assumed.

Separately: history still holds the unredacted originals — `git show` on the previous
commit returns both addresses. Removing them needs a rewrite and force push.

**What a rewrite actually buys, and costs.** There are no forks (checked Aug 10), so
nothing downstream breaks in that sense. But:

- **Existing clones keep the old objects regardless.** Roughly 53 unique cloners pulled
  this repo in the preceding fortnight — mostly automated mirrors, as any public repo
  attracts. A rewrite cannot reach any of them.
- **A careless `git pull` after a force push can put the old history back.** Anyone
  with a stale clone who merges rather than re-cloning reintroduces exactly the commits
  the rewrite removed.
- **GitHub keeps unreachable commits addressable by SHA** after a force push. They stop
  appearing in the branch, but remain fetchable by direct URL until GitHub Support is
  asked to garbage-collect them. A rewrite alone does not purge their copy.

So the realistic framing for Bill is that redaction stops *continuing* to publish the
addresses; it cannot un-publish them. A rewrite is cheap here and tidies the public
face of the repo, but is not a remedy, and should not be sold to Don or Rick as one.
If it matters to them, the honest step is telling them it happened.

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
