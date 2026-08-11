# Keycloak realm imports

Both home-base realms, imported at container startup by `start --import-realm`.
Kept here rather than clicked into the admin console so the identity layer is
reproducible and reviewable.

**No comments in these files.** Keycloak's importer rejects unrecognised
top-level fields and refuses to start the server at all — an `_comment` key is
enough to take Keycloak down with `Unrecognized field "_comment"`. Explanations
live in this file instead.

## `publisher-c-realm.json` — HB001, Publisher C's home base

The reader's home base in the demo script. Clients `pub-a` and `pub-b` are the
two content publishers; each carries `pubMbrId` as a client attribute, which the
custom mapper copies into the token.

Seeded readers are at two subscription tiers, so the demo can show one whose
subscription covers an article and another who has to buy it:

| User | `networkGroupId` | Meaning |
|---|---|---|
| susan@example.org | 4096 | Paid Subscriber |
| tom@example.org | 2 | Registered only |

## `newshare-realm.json` — HB002, the demo home base

A second, genuinely distinct home base so the chooser has a real choice in it —
its own issuer, its own JWKS, its own users. Its Retail Agent applies a
different markup (1.4 against 1.1), which is what lets the demo show two readers
paying different retail prices for the same article.

## Two things here are load-bearing

**Pairwise subject identifiers.** Every client configures
`oidc-sha256-pairwise-sub-mapper`. Without it each publisher receives the same
identifier for a reader and cross-site correlation — the thing this architecture
exists to prevent — becomes trivial.

**A different salt per realm.** `pairwiseSubAlgorithmSalt` differs between the
two realms, so a reader registered at both home bases does not collapse to one
identifier at a given publisher.

## Secrets

Client secrets, salts and demo passwords are `REPLACE-ME` placeholders in this
repository and are substituted on the host at deploy time. The committed values
are not usable and must never be treated as if they were.
