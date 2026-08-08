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
| Step 18 + wholesale-retail section: price negotiation | **Gap — largest remaining work** |
| Step 43: duplicate aggregated log reports | Partly built — reporting endpoints exist |
| AI answer-engine section (14 steps) | **Deferred by decision** — see below |

## Completed this round

**Network Discovery service** (`src/network-discovery/`) — Plan 06 implemented for real.
Serves the ITEGA registry of certified home bases and publishers, and resolves a visitor
to a home base in the order the script describes (step 20–24): exact match on Publishing
Member ID, then name match, then an IP-prefix hint, then falling back to offering a
default home base for sign-up. Also serves WebFinger (RFC 7033) and a network discovery
document. The registry lives in `data/registry.json` so ITEGA's certification decisions
stay reviewable in version control.

## Remaining gaps

### 1. Multi-home-base routing in als-auth
`GET /auth/home-bases` still returns one hardcoded Keycloak entry and `/auth/authorize`
always redirects to the single configured realm. Both need to consult Network Discovery.
The script requires Publisher C to act as a real, distinct Home Base/ASP while Publishers
A and B act only as content sites, so a second Keycloak realm is needed.

### 2. Dynamic pricing negotiation — now fully specified
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

This implies an event-schema change (a field identifying which party filed a given
report) and a negotiation exchange between the publisher's client code and the home base.

> **Defect found while reviewing this against the code.** In
> `src/als-logging/main.py`, the publisher report computes
> `SUM(page_class * markup_ratio) AS total_wholesale`. That value is the *retail*
> total, not wholesale — `page_class` alone is the wholesale price. The column is both
> mislabeled and exposed to publishers, which under the 08-07 script is precisely the
> number the Rights Owner is not supposed to learn. Fix alongside the pricing work.

### 3. First-party cookie step (Path Option 1, steps 10–11)
The script has the Authenticator look for "a first-party cookie in the ITEGA domain,"
but the architecture forbids auth cookies on publisher domains. Keycloak's own IdP
session cookie, on its own domain, already produces the behavior the script describes
and is what makes the transparent-SSO section work. Worth one clarifying question to
Bill rather than a design change.

### 4. Minor
Script step 29 specifies refusal copy for a declined payment authorization
("Your requested content is not available at this time. Please contact your ITEGA Home
Base for options.") — distinct from the existing insufficient-tier message.

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

## Open questions for Bill

1. Does "first-party cookie in the ITEGA domain" mean the identity provider's own session
   cookie, or something visible on publisher domains?
2. Should the AI answer-engine sequence be built on the current OIDC model, deferred, or
   reconsidered in light of the peer-review recommendation?
3. For Aug 25, which sections must be genuinely live versus narrated from a simulation?
