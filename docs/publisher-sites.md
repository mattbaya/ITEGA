# Publisher Sites

*The WordPress sites standing in as content publishers for the Aug 25 demo.*

No credentials appear here; this repository is public.

---

## The two sites

| Role | Site | Member ID | Home base for the demo |
|---|---|---|---|
| **Publisher A** | `barharbor.info` | `ITEGA-PA-0001` | — content publisher |
| **Publisher B** | `northberkshire.org` | `ITEGA-PB-0001` | — content publisher |

Two separately-branded local news sites on different domains. That matters more
than the number of sites: the claim the demo makes is that a reader with an
account at *one* organisation is recognised at *another*, and two sites that
visibly belong to different places carry that better than three subdomains of
one would.

A third site is not needed. The cross-publisher leg of the script — sign in at
one publisher, be recognised at the next without logging in again — is fully
demonstrated between two.

**Publisher C is not a WordPress site.** It is the reader's home base, which is a
Keycloak realm on VPS 1. It issues identities; it does not serve articles.

## Seeded content

Each site carries four articles written to fit its own patch — ferries, Acadia,
the lobster fleet and a cruise-ship cap for Bar Harbor; MASS MoCA, the Clark,
the Hoosic River restoration and a Williams College purchase for North
Berkshire.

Each article carries two pieces of post meta the plugin reads:

| Meta | Value | Why |
|---|---|---|
| `newshare_page_class` | `0.05`, or `0.20` on one piece per site | The publisher's asking price. The dearer article is what gives the price negotiation something to actually negotiate over — at $0.05 a home base simply accepts. |
| `newshare_required_bits` | `4096` | Paid-subscriber tier, so the article is gated rather than free. |

## Configuration applied

- **`siteurl` and `home` on `barharbor.info` were changed from `http://` to
  `https://`.** The plugin builds its OIDC callback with `rest_url()`, so on
  plain HTTP it would have produced an `http://` callback that could never match
  the `https://` redirect URI registered with the home base. The site already
  served HTTPS; only the WordPress setting was wrong.
- **Both Keycloak realms and the ALS publisher config** carry each site's real
  callback, `https://<domain>/wp-json/newshare/v1/callback`. These must match
  exactly or the code exchange fails with `invalid_client`.
- **The network registry** names both sites, so the demo's directory listing
  shows real publishers rather than placeholders.

## Bar Harbor: theme and styling

Moved from the `Extra` theme to the existing `divi-barharbor` child theme, with
a Downeast palette — harbour navy, brass, buoy red, spruce — serif headlines,
and a masthead over a centred nav bar.

Two things learned doing it, both worth knowing before touching these sites
again:

**Customizer CSS does not follow a theme switch.** It is stored in a per-theme
`custom_css` post, so switching themes silently leaves the styling behind. It
has to be read out and re-applied under the new stylesheet.

**On this install the Customizer CSS was never emitted at all.** The post
existed and was published, `wp_custom_css_cb` was hooked to `wp_head`, and yet
no `wp-custom-css` block appeared in the rendered page — including when fetched
from the server itself, which ruled out any cache or proxy in front. Rather than
keep digging through that pipeline, the styling now lives in the child theme's
own `style.css`, enqueued from its `functions.php`. That is where it belongs
anyway, and it is version-controlled with the theme rather than sitting in the
database.

A backup of the original child stylesheet is kept beside it as `style.css.bak`.

## WP-CLI on this host

WP-CLI runs under the system `php.ini` and reads neither `.user.ini` nor
`.htaccess`, so the generous web-request memory limit set for these sites does
not apply to it — it got 128 MB and died bootstrapping WordPress. `WP_CLI_PHP_ARGS`
did not help either, because `/usr/local/bin/wp` is a bare PHP script run through
`env php` rather than the wrapper that consults it.

Both accounts now have a `~/bin/wp` shim that invokes `php -d memory_limit=512M`
directly, with `~/bin` ahead on `PATH`. 512 MB was chosen by testing: 128, 192
and 256 all fail. Nothing pathological is behind the requirement — autoloaded
options total about 0.1 MB across ~100 rows.

## Plugin installed and verified

Both sites run the plugin, installed from a pre-built package and configured
entirely on activation — member ID, ALS and directory URLs, API key and pricing
all applied without anything being typed into a settings form.

**The access gate works.** Verified against the live site with a single reader
session across four articles:

| Read | Gate shown | Full body served |
|---|---|---|
| 1–3 | no | yes |
| 4 | **yes** | **no** |

Worth recording how that looked at first glance: an anonymous request for a
gated article returned the whole article, which reads like a broken paywall. It
is not. `newshare_free_article_count` is 3, so the first three reads are
deliberately free and the meter closes on the fourth. The lesson is that a
single anonymous request proves nothing about the gate — the meter has to be
exhausted before the gate is even asked to act.
## Still to do

- **The reader's authenticated path** — signing in through a home base, the
  price negotiation, and the purchase notice — is the remaining untested leg.
- **`greylockglass.com`** is a real, operating news site whose owner may be
  willing to take part. That would be a considerably stronger demonstration than
  two sites we control, and should only be attempted after the flow is proven on
  these two.
