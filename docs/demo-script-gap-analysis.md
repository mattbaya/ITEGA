# Aug 25 Demo Script — Gap Analysis and Build Plan

*Working document. Reconciles Bill Densmore's demo script against the prototype in `src/`.*

Source script: `reference/ITEGA-RJI-demo-script-08-07-26 document.md` (gitignored —
`reference/` holds source documents and correspondence that do not belong in a public repo).
The 08-07 revision supersedes 07-30; its main change is a fully written-out
wholesale-retail pricing section that the earlier draft left truncated mid-sentence.

## Goal

Bill's ask: confirm the scripted functionality is operationalized in the existing code,
then drive a UI-rich demo over Zoom on Aug 25. Working functionality is preferred over
simulation wherever it is achievable — a live flow is far more persuasive to the
publishers in that room than a mockup.

## Status by section

| Script section | Status |
|---|---|
| Definitions 1–13 | Covered — map onto existing roles and JWT claims |
| Steps 1–8: no-account visitor offered Network Login | Built — `templates/access-gate.php` |
| Steps 9, 12–17: redirect, session token, tier enforcement | Built — `src/als-auth/main.py` |
| Path Option 2 (steps 20–24): home base discovery | **Built this round** — see below |
| Steps 31–42: transparent SSO at a third publisher | Needs end-to-end verification, likely no new code |
| Step 18 + wholesale-retail section: price negotiation | Built; needs an end-to-end run |
| Step 43: duplicate aggregated log reports | Partly built — reporting endpoints exist |
| AI answer-engine section (14 steps) | **Deferred by decision** — see below |

## Two findings that should shape the pricing work

### X402 — corrected, and settled

> **Correction (Aug 9).** The analysis below overstated the fit. Drummond Reed
> clarified that **x402 is strictly for payments and does not do identity
> management**. The identity half is a separate, much less mature effort: `x401`
> is a *proposal* from Proof (Daniel Buchner) to layer verifiable credentials onto
> x402, published as a blog post in June 2026, and the underlying work is in ToIP's
> Decentralized Trust Graph Working Group with reference code at OpenVTC (LF
> Decentralized Trust Labs).
>
> That matters because the AI-agent section needs **authentication** first — deciding
> whether a crawler is an ITEGA member at all — and x402 would not have supplied it.
> The facilitator mapping below still holds for the *payment* leg, and is worth
> keeping in view, but x402 was never going to carry the part Bill most needs working.
>
> **Decision (Bill, Aug 8):** build our own approach now, keep the seam open, and be
> able to state that ITEGA "intends to support x402 when it becomes an operating
> standard." AI-agent support must work for Aug 25 regardless.

The mapping that remains accurate, for the payment leg:

**X402** (incubated by Cloudflare and Coinbase, now at the Linux Foundation) puts
payment into HTTP directly, and its roles map onto the four-party model closely:

| X402 | Newshare |
|---|---|
| `resource server` | CMS / content publisher |
| `client` | End User's Agent, or an AI Agent |
| `facilitator` (verifies and settles) | **the ALS** |
| `PaymentRequirements` | the publisher's asking price (`pageClass`) |
| deferred payment scheme | ITEGA's batch settlement |

The flow is an HTTP-native negotiation: the server answers a request with
`402 Payment Required` and its terms, the client returns a signed payment
payload, the server verifies — directly or through a facilitator — and then
serves the content. That is recognisably the exchange the demo script describes
in prose, expressed as a standard.

Cloudflare's proposed **deferred payment scheme** is the closest fit of all: it
decouples the cryptographic handshake from settlement so that crawlers can be
billed a single aggregated fee at the end of the day against a card or bank
account, supporting "pre-negotiated licensing agreements, batch settlements, or
subscriptions." That is ITEGA's settlement model, already standardised.

**What keeps the migration credible.** The current architecture already separates
the three things x402 would slot into: authentication (the Authenticator issues a
session token), price agreement (the publisher and the Retail Agent negotiate
directly), and settlement (a weekly batch reading the log). Payment is already
decoupled from identity, so adopting x402 later means replacing the price-agreement
and settlement legs without touching how readers are authenticated. That makes
"we intend to support x402" an architectural statement rather than a hopeful one —
worth being able to say plainly on Aug 25.

### Rick Lerner questions the premise of price negotiation

Rick Lerner — co-inventor of the original system — pushed back on the dynamic
pricing idea in his May review of Bill's essay:

> "I think you need to suggest why any publisher would want to have to negotiate
> prices, rather than just set them and adjust to maximize demand. I always
> thought the original idea was that each publisher set their own price."

He also notes they "never came up with a way to present prices in a way that let
consumers choose which provider they wanted to use," and warns more broadly that
leaving publishers to invent their own pricing models "is where I think we went
wrong."

This does not block the work — the script specifies negotiation clearly and it is
demonstrable. But the person who built the original system is unconvinced
publishers want it, so it is worth Bill reconciling the two views before the
roundtable, where Rick's question ("why would a publisher want to negotiate?")
is likely to be asked from the floor.

Separately, Rick argues the AI problem "should be handled separately from
consumers... publishers are more likely to want to fix that problem without
uprooting their consumer relationships." That independently supports both
deferring the AI section from the consumer flow and treating it as its own
track — which is what X402 would allow.

## Completed this round

**Network Discovery service** (`src/network-discovery/`) — Plan 06 implemented for real.
Serves the ITEGA registry of certified home bases and publishers, and resolves a visitor
to a home base in the order the script describes (step 20–24): exact match on Publishing
Member ID, then name match, then an IP-prefix hint, then falling back to offering a
default home base for sign-up. Also serves WebFinger (RFC 7033) and a network discovery
document. The registry lives in `data/registry.json` so ITEGA's certification decisions
stay reviewable in version control.

**Multi-home-base routing** (`src/als-auth/`) — the ALS no longer assumes one Keycloak
realm. Home bases come from Network Discovery, each with its own JWKS cache, token
endpoint, and issuer, so Publisher C can act as a genuine Home Base/ASP distinct from the
content-vending publishers. An unhinted visitor now gets the chooser from Path Option 2:
pick a certified member, look one up by name or Publishing Member ID, or be offered a
place to sign up when nothing matches.

**Retail Agent service** (`src/asp-agent/`) — the home base's buying code, as its own
party. It holds the markup ratio, answers a publisher's asking price with accept,
counter, or decline, and files its own log report for purchases it authorises. All
three outcomes tested, including that the markup never appears in a response to the
publisher.

**Price negotiation in the plugin** — publishers now ask before vending, answer a
counter-offer against a configurable floor, and show the script's refusal message when
payment is not authorised.

**Settlement pricing corrected** — see the defect note under pricing below. Wholesale is
now settled correctly and the markup is no longer disclosed to publishers.

**A fatal parse error fixed** — `class-newshare-oidc.php` declared a return type PHP
rejects, so the file did not parse and the plugin could not load on any supported PHP
version. Found by linting; it would have stopped the demo dead.

*Still needed to exercise the above end to end:* a second Keycloak realm representing
Publisher C's home base. The code paths are in place and tested against the discovery
registry; the realms themselves are a deployment step.

## Remaining gaps

### 1. Dynamic pricing negotiation — built, not yet exercised end to end
The 08-07 script defines this properly, and it is more than a static price lookup:

- **Three outcomes must all be demonstrated**: the End User accepts the offered price,
  declines it, or opens a bargaining session with the Content Server.
- **The Markup Ratio is confidential to the Retail Agent.** The script is explicit that
  the Rights Owner "does not need to know the Markup Ratio, and may or may not be
  permitted by governance or law to know it." The retail price is the Retail Agent's
  business, not the publisher's.
- **Both parties log independently.** The Content Server and the End User's Agent each
  send an enhanced log report to the logger, specifically so discrepancies and fraud can
  be audited. The Agent's report carries the markup ratio applied; the amount the End
  User's Agent owes at settlement is the *wholesale* price.

**Now built.** A Retail Agent service (`src/asp-agent/`) represents the home base's
buying code and answers accept, counter, or decline; the WordPress plugin negotiates
before releasing content and shows the specified refusal message when payment is not
authorised. All three outcomes are tested, and the markup is not disclosed to the
publisher in any response.

Dual reporting is in place: events record which party filed them, settlement
aggregates the publisher's side, and the agent's record remains as the audit
cross-check. (Worth noting because it briefly wasn't — with both parties filing and
nothing distinguishing them, settlement would have billed every negotiated purchase
twice.)

Remaining: **exercising it end to end** against a running WordPress site and home
base. The service logic and money math are verified directly; the full path is not.

### 1b. Deferred: home-base-specific pricing policy
Each home base currently reads one policy from configuration. The demo only needs one
home base making decisions, but a network with several would want per-home-base policy
storage. Not needed for Aug 25.

> **Defect found and fixed while reviewing this against the code.** The settlement
> engine treated `pageClass * markupRatio` as the wholesale value. That is the
> *retail* price — `pageClass` alone is wholesale. The consequence was not cosmetic:
> publishers were credited the marked-up amount and home bases debited it, so the
> home base's margin was paid to the publisher. That margin is the home base's whole
> incentive to send a reader to another publisher, so the code inverted the business
> model the demo exists to show. `plans/04` already described the correct flow.
> Publisher-facing reports also carried markup-derived totals, which the 08-07 pricing
> rules say the Rights Owner is not entitled to see. Both corrected; verified against
> the script's own example (100 accesses at $0.10 with a 1.1 markup now settle $10.00
> to the publisher, not $11.00).

### 1a. Verifying transparent SSO across three publishers (steps 31–42)

No new code is expected here — every `/auth/authorize` call now routes through the
reader's home base, and that home base's own session keeps a second publisher's login
transparent. But this has never been exercised with three publishers in sequence, and
nothing in the ALS explicitly guarantees it, so treat it as unverified until walked
through:

1. Sign in at Publisher B via Network Login; confirm a session token is issued.
2. Without signing out, visit Publisher A and request paywalled content. Expect no
   login prompt — the home base should recognise the reader and issue a fresh token.
3. Repeat at Publisher C. Confirm the PPID differs at each publisher (that is the
   privacy guarantee) while the reader is never asked to log in again.
4. Wait out the session token TTL and repeat step 2. Expect a silent re-authentication,
   not an error.

If step 2 prompts for login, the cause is almost certainly home-base session
configuration rather than ALS logic — check the SSO session lifetime on the realm
before changing any code here.

### 2. First-party cookie step (Path Option 1, steps 10–11)
The script has the Authenticator look for "a first-party cookie in the ITEGA domain,"
but the architecture forbids auth cookies on publisher domains. Keycloak's own IdP
session cookie, on its own domain, already produces the behavior the script describes
and is what makes the transparent-SSO section work. Worth one clarifying question to
Bill rather than a design change.

### 3. Refusal copy (script step 29) — done
Built as part of the pricing work, in its own template
(`templates/payment-declined.php`) rather than folded into the tier-upgrade gate,
since the two situations call for different remedies.

## Deferred by decision: AI answer-engine section

The script's 14-step machine-to-machine sequence (AI agents authenticating, confirming a
price per request, and streaming content until a timeout) is **not being built this
round**. It has no counterpart in the current architecture and would be built from
scratch.

It also sits on one side of a disagreement the project's own peer reviewers already had:
Drummond Reed's February review argued specifically that AI agents "don't use browsers,
don't use OpenID" and need DID/VC-based infrastructure, whereas the script extends the
existing OIDC session-token model to cover them. That is a legitimate choice, but it
should be Bill's explicit call before engineering time goes into it.

Note this is not a peripheral request: the E&P op-ed and the RJI event page both lead
with AI agents paying for content, so it will likely come up on Aug 25 even if it isn't
demonstrated.

## Answered by Bill (Aug 8–9)

1. **X402** — build our own approach now; keep the seam open; state that ITEGA intends
   to support x402 when it becomes an operating standard. AI-agent support ships for
   Aug 25 regardless, because the handshake for authentication, logging and settlement
   is central to ITEGA's pitch to publishers. See the correction above: x402 is
   payments-only and would not have covered the authentication half anyway.
2. **Price negotiation** — a settled business decision, build it. Refined flow: the
   publisher posts a price, waits a very short interval for the agent to accept or ask
   to negotiate, then either negotiates or declares the posted price take-it-or-leave-it.
   Rick's scepticism is exactly why it needs to be demonstrable — that is how you elicit
   the feedback.
3. **First-party cookie** — resolved by adding a step *before* step 10: the Authenticator
   first checks its own cached store of authenticated readers and reuses a still-fresh
   token, falling back to steps 10–14 only when stale. Wanted as working code. Multi-
   authenticator coordination at scale is explicitly out of scope for Aug 25.
4. **Session token lifetime** — Bill proposed 30 minutes; the implementation already uses
   exactly that (`session_token_ttl` = 1800s). Short enough to limit replay, long enough
   that a live demo will not re-authenticate mid-sentence.
5. **Publisher naming** — Publisher C and "Publisher 3" are the same party, as are A/B and
   1/2. Settling on **letters** throughout, since the script's Definitions section
   establishes them.
6. **Aug 25 scope** — the full system operating across three publishers, plus a
   step-through demo narrating the background exchanges in pop-ups and closing on what is
   logged where and how settlement works, markup included.
