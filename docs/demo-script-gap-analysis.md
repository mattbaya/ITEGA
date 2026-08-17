# Bill's demo script vs. what is built

*Reviewed against `ITEGA-RJI-demo-script-08-07-26` (the 08-07 revision, in
`reference/`, gitignored). Last checked 2026-08-17 against the live deployment.*

Everything marked **met** below was exercised against the running system, not
read out of the source. Where a claim rests on a test, the suite is named.

---

## Verdict in one paragraph

The script has four movements — the reader's journey, transparent login at a
further publisher, AI answer engines, and wholesale-retail pricing. **All four
work end to end against live services.**

Of the five gaps first recorded here, **two are now closed**: there is a third
content site (Gap 3), and the sign-up link that led to a login form now
registers people properly (Gap 5, issue #25). Three remain, of which one is
cosmetic but highly visible on the day and one is the missing screen that
carries Bill's most important argument to publishers.

---

## Section by section

### Definitions (1–13) — met

The vocabulary maps cleanly onto what exists. `Publishing Member ID` is
`pubMbrId`; CMS is the WordPress plugin; ASP is the Retail Agent; Home Base is a
Keycloak realm.

One deliberate divergence: the demonstration no longer keeps an ASP-only member.
All three organisations act as both CMS and ASP, which the Definitions expressly
permit ("operating as either an ASP, a CMS, or both") and which keeps a viewer
from meeting five organisations when the story has three.

### Demonstration flow 1–5, 9 — met

The meter allows three free reads and closes on the fourth; the gate offers the
network; the Authenticator holds the requested resource while the reader is away
and returns them to it. `journey-test.py`.

### Path Option 1 — first-party cookie (10–14) — met, with one deliberate difference

There is a first-party cookie on the ITEGA domain, and a returning reader is
recognised without a second sign-in.

**The difference is worth Bill knowing, because it is an improvement and he may
want to say so.** The script describes the cookie as *containing* an ITEGA-issued
User Member ID, which itself contains the reader's member ID at their home base
and the Publishing Member ID of that home base. Ours contains **an opaque handle
and nothing else**; the mapping lives server-side at the Authenticator.

Identifiers in a cookie can be read by anything that can read the cookie, and a
value that carries the home base's identity inside it tells every party who holds
it where that reader banks. The handle cannot be decoded, cannot be correlated,
and expires. The behaviour the script asks for is identical; the disclosure is
not.

### Path Option 2 — discover the home base (20–23) — met

The chooser asks for the home base by name or Publishing Member ID, suggests
candidates from the visitor's IP, and offers a default home base for sign-up when
nothing matches.

### Using the session token (25–30) — met

Token stored temporarily, attached, resubmitted; the publisher checks its asking
price and opens a dialog with the reader's home base before vending. All three
outcomes — accept, counter, decline — occur in the real reader flow, and the
refusal copy is Bill's own wording from step 29, with a link back to the home
base.

### Transparent login to a third publisher (31–42) — met

Sign in at Bar Harbor, cross to North Berkshire, cross again to West End
Sentinel: no password, no second chooser, and the gated article is served each
time. The three publishers know the reader by three unrelated opaque
identifiers, which is checked explicitly rather than assumed.

**Gap 3 is closed.** `wesmc.org` is a third content site, so the section's
literal staging is now met as well as its claim. Each of the three is also a
home base, which additionally demonstrates the Definitions' allowance that a
member may act as ASP, CMS or both.

### User reports (43) — met

The home base can pull the full clickstream for its own readers; a publisher gets
aggregated totals only, and never the markup. The reader sees their own purchase
record in the dashboard. Settlement writes both JSON and per-home-base CSV, which
is the "format for such data" the step asks to be presented.

### AI answer engines (1–14) — met, including the part nothing tested until today

Verified live during this review against a real Bar Harbor article:

| Step | Behaviour | Result |
|---|---|---|
| 3–4, 14 | Non-member crawler | **403**, with a note directing it to join |
| 5–6 | Member, no price agreed | **402**, quoting $0.05 |
| 7 | Member accepts the price | **200**, article served, grant issued |
| 9–11 | Second resource, presenting the grant | **200**, served without renegotiating |

Steps 9–13 — continuing to crawl under a grant until it times out — had no test
covering them before this review. They work.

### Wholesale-retail pricing (1–10) — met, and precisely

Step 8 is the subtle one, and it is implemented exactly as written. Both parties
file their own log report. The publisher's record carries the wholesale price and
**no markup ratio at all**. The Retail Agent's record carries the markup ratio
*and* states the price owed as the wholesale figure — which is what the script
specifies, and what makes independent audit possible without disclosing the
margin. The publisher is paid $0.05 whichever home base the reader belongs to,
while readers at the 1.1 and 1.4 home bases are billed $0.055 and $0.07.

---

## The five gaps

### Gap 1 — the service hostnames in the script do not exist

The script names `Authenticator.itega.org` and `Logger.itega.org` throughout.
Neither resolves. Everything runs under `als.itega.org`.

This is cosmetic and it is also the most visible thing on the list: anyone
following Bill's script while watching a screen will see a hostname that is not
the one he just said. Fixing it is a DNS record and a vhost alias per name, and
it costs nothing.

**Recommendation:** add `authenticator.itega.org` and `logger.itega.org` as
aliases before the 25th. Keep `als.itega.org` working.

### Gap 2 — the publisher's own paywall is not offered alongside the network

Steps 6–8 stage three outcomes at Publisher B: an invitation to take out a *local*
subscription, a second option to log in to the ITEGA network, and — if neither is
taken — a page saying the resource is not available.

Our gate offers only the network login.

This is the smallest change on the list and the one with the most riding on it.
Steps 6–8 are where Bill demonstrates that **ITEGA does not replace a publisher's
paywall and does not take their subscriber** — the first objection any publisher
in the room will have. Right now the demo shows a gate whose only exit is the
network, which argues the opposite of what he intends.

**Recommendation:** add a configurable "Subscribe to *this* paper" button beside
the network button, and the refusal page for the reader who takes neither. Half a
day.

### Gap 3 — CLOSED. There is a third publisher.

Steps 31–42 are titled "transparent login to publisher number three", and step 35
sends the reader to "Publisher 3".

But step 3 of the same script says Publisher C "performs only as an ASP", and the
established mapping is that Publisher 3 *is* Publisher C. A party that only keeps
accounts cannot also serve the article that section requires.

The demonstrable claim — sign in once, be recognised at another publisher without
a password — is fully met between Bar Harbor and North Berkshire. What is not met
is the literal staging of a third content site.

**Resolved by building it.** `wesmc.org` — West End Sentinel Media Cooperative —
is the third content site, and is also a home base. The self-contradiction in the
script no longer matters: every publisher named is a destination that serves
articles, and Publisher C's ASP-only role is filled by the same organisations
wearing their other hat.

### Gap 4 — the sign-up invitation is a sentence, not a screen

Step 24 asks for "a marketing screen briefly acquainting them with the ITEGA
network and inviting them to establish an ITEGA-compliant account". The chooser
currently offers one line: *Not affiliated with a member yet? Create an account
with …*.

Functionally correct, rhetorically thin — and this is the screen a reader with no
home base actually sees, which makes it the network's only pitch to a newcomer.

**Recommendation:** two or three sentences and the four-party picture. An hour.

### Gap 5 — CLOSED. Sign-up now registers people.

The chooser's "Create an account with ..." link pointed at Keycloak's bare
registration endpoint, which cannot build a flow without OIDC parameters and so
quietly served the **sign-in** page instead — a reader told to create an account
was shown a password box. `/auth/signup` now builds the same request a sign-in
builds, aimed at the registration screen, and carries the reader back to the
article they wanted. Issue #25.

### Gap 6 — a home base cannot be found by URL

Step 24 says the reader may be asked for their home base's URL, and that a URL
matching a member ASP should invite sign-up there. We resolve by name and by
Publishing Member ID; a URL falls through to the default. Small, and easy.

---

## Settled previously, still true

- **X402** — corrected and settled; the AI handshake uses plain HTTP 402 with
  ITEGA headers, not the x402 payments protocol.
- **Rick Lerner's objection to price negotiation** — the demo supports both:
  `terms=final` posts a take-it-or-leave-it price and never counters,
  `terms=open` negotiates. Both are demonstrated.
- **Publisher letters beat numbers.** A/B/C everywhere; the script's 1/2/3 are
  the same parties.
- **Home-base-specific pricing policy** remains deferred by decision.

---

## What to do before the 25th, in order

| | Gap | Cost | Blocking? |
|---|---|---|---|
| 1 | Hostname aliases (Gap 1) | ~1 hour | No, but visible |
| 2 | Publisher's own subscribe option + refusal page (Gap 2) | ~half a day | **Carries the argument** |
| 3 | ~~Third publisher~~ — built: wesmc.org | done | — |
| — | ~~Sign-up leads to a login form~~ — fixed (#25) | done | — |
| 4 | Sign-up screen (Gap 4) | ~1 hour | No |
| 5 | Resolve a home base by URL (Gap 5) | ~1 hour | No |
