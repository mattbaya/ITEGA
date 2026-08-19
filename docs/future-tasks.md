# If this becomes more than a demonstration

Everything here is deliberately **not** built. The prototype's job is to prove
the four-party exchange works end to end, and it does. This is the list of what
would have to be true before the same code carried a real newspaper's revenue —
kept in one place so the demonstration's shortcuts are visible rather than
forgotten.

Nothing here blocks Aug 25. Several items would block a Missouri pilot.

---

## 1. Somewhere to test that is not production

Every destructive check in this project has been run against live sites we
happen to own. Credentials were deleted from `wesmc.org` to prove a site
re-certifies itself; a demonstration account carried a zero spending cap for a
minute; barharbor.info was pinned to an old plugin version to prove the update
path. All were restored, and all were defensible only because the sites are ours.

Against a real newspaper, none of it is.

**What it needs.** Not a second network — the expensive parts are already
`docker compose` definitions, and the plugin provisions itself from a registered
domain. What is missing is a second registry, a throwaway domain, and a
documented teardown. The one piece that cannot be faked is a publisher site the
plugin can be *broken* on, since most interesting faults have been in the plugin
and its interaction with WordPress.

**The cheaper half is already in place.** Run `infra/journey-test.py`
immediately after every service deploy. It caught a total sign-in outage in
about a minute when 29 smoke checks did not.

---

## 2. Credentials that are scoped, rotated, and recoverable

- **The Retail Agent authenticates to Keycloak with admin credentials.** It needs
  `view-users` and `view-clients` and nothing else. A dedicated client with a
  service account, before anything carries real money.
- **Pairwise salts exist in one running Keycloak** and in one 0600 file beside
  it. Losing them costs no reader and no settlement, but every publisher would
  meet every reader as a stranger, permanently. They need a real backup and a
  decision about whether they are ever replayed on import.
- **Client secrets are per home base** now (#23) but still hand-managed. A
  network of any size needs issuance and rotation that is not a person editing
  a file.
- **API keys never expire.** A publisher's logging key is good forever. Short
  lifetimes with automatic renewal — the Let's Encrypt pattern this project
  already reasons by — would make a leaked key a finite problem.

---

## 3. Settlement that actually moves money

Reports are generated and balances are correct. No money moves. Before it does:

- An accounting trail that survives a database restore, and reconciliation
  between what a publisher filed and what the exchange recorded.
- A dispute path. Today a publisher who thinks a figure is wrong has a page and
  no recourse.
- Tax, and the question of who is the merchant of record — a governance
  question that engineering cannot answer.
- Real payment rails. Stripe Connect and ACH are in the plans; neither is built.

---

## 4. Operations

- **A deploy path for VPS 1 and VPS 2** in the shape of the plugin's: ship,
  verify against the live endpoints, and be able to go back. Today it is
  `git pull` and `docker compose up -d --build` by hand.
- **Backups.** Postgres, TimescaleDB, Keycloak realms, provisioning records.
  Nothing is backed up on a schedule. This is the single largest gap between the
  prototype and something a publisher could rely on.
- **Alerting.** Beszel watches the hosts. Nothing watches whether readers can
  sign in, or whether events are still being filed — and #50 showed a site can
  look perfectly healthy while filing nothing at all.
- **Log retention and a privacy policy for the access log.** It records what
  people read. Nobody has decided how long that is kept.

---

## 5. The reader's side

- **Reports by email** (#59) — built, but a reader's report is a list of what
  they have read arriving in an inbox, and that deserves a policy rather than a
  default.
- **Per-category limits.** Needs publishers to describe content in terms a home
  base can act on, which is a protocol question rather than a feature.
- **Account deletion, and what happens to a reader's history.** Pairwise
  identifiers make the exchange's copy anonymous; the home base's map is not.
- **A reader with more than one home base.** The architecture allows it; nothing
  in the current flow contemplates it, including the refusal screen, which
  assumes there is one place to take it up.

---

## 6. Scale

None of this is urgent for 3–5 newspapers and 50 readers, and all of it is
wrong for 500.

- The pairwise reverse index is computed as users × clients on demand. Fine for
  fifty readers; a network of millions would record identifiers at issue time
  instead.
- The period-cap tally is one Keycloak write per purchase.
- The logging service returns a home base's entire clickstream in one response,
  and the agent filters it. That wants a query rather than a filter.
- One Keycloak, one Postgres, one of everything. No replication anywhere.

---

## 7. Governance, which is not engineering's to decide

Recorded here because the code cannot proceed without answers.

- **What a home base may tell a reader about a refusal**, and who is accountable
  for the wording. The mechanism can carry a reason from the home base; nobody
  has decided whether it should.
- **Whether a declined reader may try another home base**, or take the
  publisher's own subscription. "Take it up with your home base" cannot be the
  only exit forever.
- **What the member agreement says** about a publisher's own readers never being
  gated (#41), and about markup remaining undisclosed.
- **Who may read the access log, and for how long.**
