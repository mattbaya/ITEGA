# Newshare Network — WordPress plugin

Lets a WordPress site accept readers who hold an account at any other
newspaper in the network, be paid for what they read, and never learn who they
are.

**Download:** <https://dashboard.itega.org/plugin/newshare-network.zip>
**Publisher-facing documentation** lives at
<https://dashboard.itega.org/plugin/> — that is the page to send a publisher
to, and the one the plugin's settings screen links to. This file is for people
working on the code.

---

## What it is

A WordPress plugin (PHP 8.1+, WP 6.0+) that turns a news site into a
**Content Provider** in the four-party model: it meters anonymous reads, offers
the network alongside the publisher's own subscription, accepts a session
vouched for by the reader's home base, negotiates a price, serves the article,
and files its own record of the sale.

It also answers machines: an AI answer engine that is a network member can buy
an article over plain HTTP 402 rather than scraping it.

## Installing it as a publisher would

```
Plugins → Add New → Upload Plugin → newshare-network.zip → Activate
```

There is nothing to configure. See [Self-provisioning](#self-provisioning).

Build the distributable with `infra/build-publisher-plugin.sh`, and deploy to
the demonstration sites **only** with `infra/deploy-publisher-plugin.sh <site>`
— never by copying single files. That restriction exists because copying one
file after it gained a constructor argument took barharbor.info down
completely.

## Self-provisioning

The distributable is a public download, so it contains no credentials. Instead:

1. ITEGA registers the publisher's domains — the certification step
2. On activation the plugin publishes a random nonce at
   `/.well-known/newshare-challenge`
3. It calls `POST https://network.itega.org/provision` with `{domain, nonce}`
4. The discovery service fetches that URL **over HTTPS, following no
   redirects**, and compares the body exactly
5. Only then does it return the Publishing Member ID, a per-publisher API key,
   the service endpoints, and a demonstration key

This is ACME's HTTP-01 challenge. A domain arriving as a parameter is a claim;
only the site itself can answer for it. Because control is re-proved on every
attempt, **reinstalling works** and needs no operator involvement.

The call is scheduled a few seconds after activation rather than run inline —
activation happens during the plugin-upload request, and this waits on the
exchange fetching a URL back from the site.

Server side: `src/network-discovery/provisioning.py`.

## Demo mode

Lets the plugin be installed on a real, operating news site without any of its
behaviour reaching that site's ordinary readers. When enabled, every
reader-facing behaviour is suppressed unless the visitor opted in with the
demonstration key:

- no access gate, whatever a post's `required_bits` say
- no price negotiation
- nothing sent to the exchange
- no RSL metadata in the page head

**Every uncertain case resolves to "not a participant"** — missing key, blank
key, mismatch, malformed cookie. The worst outcome of a bug here should be that
the demonstration does not run, never that a real reader is gated.

Ships **on**, with the key issued by provisioning rather than invented by the
publisher.

That is deliberately stronger than leaving prices at zero, which is inert only
until somebody saves a price on one post.

## The guest role

Network readers get a WordPress user — the session lives in user meta, which is
how the access check knows they are entitled — with the role
**`newshare_guest`** ("ITEGA Guest"), holding exactly one capability: `read`.

Not `subscriber`. A publisher's subscriber role is theirs, and plugins
routinely add capabilities to it; a network reader landing in that role would
inherit access nobody decided to grant. The dedicated role also makes these
accounts a visible group in the users list, which matters when the site belongs
to someone hosting this as a favour.

`uninstall.php` removes the settings and the role but **not** the accounts —
they may have comments attached, and that is the site owner's decision.
Deactivation changes nothing.

## The publisher's own readers

Anyone signed in to the WordPress site who did not arrive through the network
reads everything on it. No meter, no gate, no price quote, no log report.

This is Jason Velazquez's question at Greylock Glass, and the answer has to be
unconditional: he has monthly contributors, and a plugin that started charging
the people who already pay him would be worse than no plugin. A newspaper's own
relationships are not the network's to intermediate — the network exists for
visitors from elsewhere. Subscribers, members, contributors and staff are all
covered by the same rule, whatever roles the site's own membership plugin
invented for them.

Network accounts are always separate: `find_or_create_user()` derives its
username from the `networkUserId` and never adopts a local account by email, so
a monthly contributor who also joins the network keeps two unrelated identities
— which is the point of pairwise identifiers, and means joining costs them
nothing at their own paper.

The check reads the role as well as the link meta. A network account holds
`newshare_guest` and nothing else, so if its meta is ever lost — a partial
write, a restore, a manual edit — reading the meta alone would silently promote
that reader into the publisher's own audience with the run of the site. Two
signals, and it fails towards the gate.

## The status badge

Every page tells a reader whether they are signed in to the network:
`ITEGA Guest 948AFC` with a way out, or `Not signed in` with a way in.

It exists because the answer used to depend on the theme. WordPress's admin
bar rendered on one site and not another, so the same reader saw their status
at one newspaper and nothing at the next — and reading several articles
without being stopped looks exactly like a broken paywall. The admin bar was
never the right place for this: it is WordPress chrome, it says "Howdy", and
it is silent about the network when a visitor is signed out.

**Demo mode suppresses it entirely**, checked before any markup is emitted. A
publisher hosting this quietly must stay quiet, and a badge on every page
would be the most visible way to break that promise. Verified by switching
demo mode on against a live site: zero badge markup, zero gate.

`newshare_show_status_badge` turns it off without turning the plugin off.

## Publishing a new version

```bash
infra/publish-plugin.sh
```

Lints, packages, writes the update manifest, uploads both, and then checks
what is actually served against what was built. Run it for **every** plugin
change, without exception.

The reason is not tidiness. Greylock Glass installed a build that was one hour
stale, and the consequences were invisible to them: their demonstration key
was never issued, and two of our asset URLs sat in their page source. Nobody
could have noticed, because until 0.2.1 the plugin had no way to say a newer
version existed.

`class-newshare-updater.php` reads `update.json` and reports newer versions
through WordPress's own update machinery, so a publisher sees the ordinary
"update available" notice and presses the ordinary button. Bump the version in
the plugin header, then run the script; the manifest takes its version from
the header, and the script refuses to finish if the two disagree.

## Files

| File | What it does |
|---|---|
| `newshare-network.php` | Bootstrap, activation, role registration, hooks |
| `includes/class-newshare-provisioning.php` | Serves the challenge, fetches credentials |
| `includes/class-newshare-demo-mode.php` | Suppresses everything for non-participants |
| `includes/class-newshare-session.php` | Session claims in user meta |
| `includes/class-newshare-oidc.php` | The RP flow, through the ALS |
| `includes/class-newshare-access.php` | The meter and the gate |
| `includes/class-newshare-pricing.php` | Asking price, negotiation, refusal |
| `includes/class-newshare-logger.php` | Files the publisher's own record |
| `includes/class-newshare-ai-agent.php` | 403 / 402 / grant for answer engines |
| `includes/class-newshare-logout.php` | Sign out here vs everywhere |
| `includes/class-newshare-status.php` | The network status badge |
| `includes/class-newshare-updater.php` | Offers updates through WordPress |
| `includes/class-newshare-rsl.php` | Rights metadata |
| `includes/class-newshare-admin.php` | Settings screen, links to the docs URL |
| `uninstall.php` | Removes settings and role on delete |

## Options

Read `newshare_*` options; all are created on activation with `add_option`, so
an existing configuration is never overwritten by a reactivation or upgrade.

| Option | Default | Meaning |
|---|---|---|
| `newshare_pub_mbr_id` | *provisioned* | Publishing Member ID |
| `newshare_als_api_key` | *provisioned* | Per-publisher key; may only file events under its own member ID |
| `newshare_demo_mode` | `1` | Suppress everything for non-participants |
| `newshare_demo_key` | *provisioned* | Opts a visitor in |
| `newshare_free_article_count` | `3` | Reads before the meter closes |
| `newshare_default_page_class` | `0.05` | Asking price for unpriced articles |
| `newshare_premium_page_class` | `0.20` | Suggested premium rate |
| `newshare_minimum_page_class` | `0.02` | Lowest counter-offer accepted |
| `newshare_posted_price_is_final` | `''` | Refuse to negotiate |
| `newshare_default_required_bits` | `0` | `4096` gates to paid subscribers |
| `newshare_default_rsl_tag` | `CC-BY-NC` | Rights tag |

`NEWSHARE_PUB_MBR_ID` and `NEWSHARE_ALS_API_KEY` in `wp-config.php` win over
the database.

Per post: `newshare_page_class` and `newshare_required_bits`.

## Things worth knowing before changing it

**The asking price is the publisher's, and lives only here.** `pageClass` is
what the publisher is owed. The reader's bill is that times the home base's
`markupRatio`, which is the home base's margin and **must never be disclosed to
a publisher**.

**A single anonymous request proves nothing about the gate.** The first three
reads are free by design, so the meter has to be exhausted before the gate is
even asked to act. An anonymous request returning a whole article looks like a
broken paywall and is not.

**Relying on the site-wide price default is how issue #18 hid.** It left 9,770
articles readable by anyone across two sites, and no test noticed for weeks,
because the test asked the site for priced articles and then checked those were
priced.

**The plugin is deployed as a unit.** See `infra/deploy-publisher-plugin.sh`;
`NEWSHARE_DEPLOY_FORCE_FAIL=1` rehearses its rollback against a healthy site.

## Testing

From the repository root, against the live deployment:

```bash
infra/journey-test.py    # 18 checks — the reader's journey, at every publisher
infra/logout-test.py     # 19 checks — both sign-out scopes actually differ
infra/smoke-test.sh      # 28 checks — every public surface
```

Assert on what the reader ends up with, never on the redirect that points at
it. A 302 towards a login page is not a login.
