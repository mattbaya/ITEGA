# Publisher Sites

*The WordPress sites standing in as content publishers for the Aug 25 demo.*

No credentials appear here; this repository is public.

---

## The three sites

| Site | Publisher ID | Home base | Markup |
|---|---|---|---|
| `barharbor.info` | `ITEGA-PA-0001` | Bar Harbor Info (`publisher-c`) | 1.10x |
| `northberkshire.org` | `ITEGA-PB-0001` | North Berkshire (`newshare`) | 1.40x |
| `wesmc.org` | `ITEGA-WESMC-0003` | West End Sentinel (`wesmc`) | 1.25x |

**Each of the three is both a publisher and a home base.** Bill's Definitions
allow a member to operate as ASP, CMS or both, and nothing was demonstrating the
third case. It also keeps the cast small: a viewer meets three organisations
rather than five.

Three separately-branded sites on different domains, which matters more than the
count: the claim is that a reader with an account at *one* organisation is
recognised at *another*, and sites that visibly belong to different places carry
that better than subdomains of one would.

`wesmc.org` is an addon domain under the `northberkshire` account, so it shares
an ssh login but not a document root — `infra/deploy-publisher-plugin.sh` knows
the difference.

## Seeded content

Bar Harbor and North Berkshire carry their real archives — 7,751 and 1,950
published posts — and West End Sentinel 122. **Every published post on all three
carries an explicit price**, which is the fix for issue #18: relying on the
site-wide default left 9,770 articles readable by anyone, and no test noticed.

**West End Sentinel's articles are about real events**, researched and written
originally with claims attributed — not invented, and not copied from anyone.
Both halves matter: a project arguing that journalism should be paid for cannot
demonstrate itself on fabricated reporting, and cannot demonstrate itself on
republished copy either.

Fourteen of them were briefly unpublished on the assumption that a run of crime
headlines naming real Boston venues had to be fabricated. All fourteen were
real, with mainstream coverage, and are restored. If content here looks wrong,
check a source before removing it, and draft rather than delete.

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
- **The network registry** names all three sites, so the demo's directory listing
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

## North Berkshire: newspaper front page

The site was fronted by an events calendar — a community noticeboard, with the
stock Divi "D" as its logo and every page auto-listed in the nav (News, Sources
and Events each appeared twice). It did not read as a newspaper, which matters
because the whole claim being demonstrated is about paying publishers for
journalism.

Now:

- **`page-newspaper.php`** in the child theme — a broadsheet front: nameplate,
  dateline, lead story with a drop cap, three columns beneath. Stories are
  selected by the presence of `newshare_page_class`, which is exactly the set of
  articles seeded and priced for the demo, so event posts never appear.
- **`assets/css/newspaper.css`**, enqueued only on that template. Ink on
  newsprint with one Berkshire green; column gutters are hairline rules.
- **A masthead logo** — a low ridge line over the wordmark, with
  `MASSACHUSETTS` letterspaced beneath. Set as both the Divi header logo and the
  site icon.
- **A real primary menu.** There was no menu assigned to `primary-menu` at all,
  which is why Divi was auto-listing every page and producing the duplicates.

Two things worth knowing for next time:

**`wp option patch` cannot write into Divi's settings array** — it returns
`Cannot create key ... on data type NULL`. Use `wp eval` and
`get_option`/`update_option` directly.

**The Divi logo lives in `et_divi[divi_logo]`**, not in a theme mod.

## Demo accounts

Both realms use the **email address as the username**
(`registrationEmailAsUsername` is on), so `--username` lookups against a plain
handle silently find nothing. Set passwords by user id.

The Keycloak admin account is **not** `admin`; read the real one from
`KEYCLOAK_ADMIN` in the container environment. `kcadm.sh` fails quietly when the
login was rejected, so every subsequent command appears to do nothing.

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

All three sites run the plugin, installed from a pre-built package and
configured entirely on activation — member ID, ALS and directory URLs, API key and pricing
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
## Updating the plugin

Use `infra/deploy-publisher-plugin.sh <site>`, or `all` for both. It is the only
supported route, and it does not accept a file path — only a site name.

```bash
infra/deploy-publisher-plugin.sh all
```

That restriction is the point. Copying `class-newshare-access.php` on its own,
after it had gained a constructor argument the deployed bootstrap knew nothing
about, took barharbor.info down completely: WordPress fatals during plugin load,
so every page on the site returned a critical error, including the front page.
The script lints every PHP file locally first, ships the directory as a unit,
then fetches real pages and greps the tail of `debug.log` for a fresh fatal. If
anything fails it restores the previous copy, parks the broken one at
`newshare-network.failed`, and re-checks that the site is actually back.

`NEWSHARE_DEPLOY_FORCE_FAIL=1` makes the verification report failure while the
code being deployed is good, so the rollback path can be rehearsed against a
healthy site without a reader ever seeing a fault.

The publisher's own `newshare-config.php` — member ID and API key, written at
install time and never in the repository — is carried across the swap.

Running it also revealed the two sites had drifted apart, 400K against 436K,
from the earlier file-by-file copying. They are identical now.

## The reader's authenticated path — verified

No longer the untested leg. Signing in through a home base, the price
negotiation, the purchase notice, crossing to the second publisher, and both
sign-out scopes are all exercised by `infra/journey-test.py` and
`infra/logout-test.py` against these two live sites.

## Still to do

- **`greylockglass.com`** is a real, operating news site whose owner may be
  willing to take part. That would be a considerably stronger demonstration than
  three sites we control. The demo-mode gate that makes it safe — ordinary readers
  see no gate, no login prompt, no pricing call, and nothing in the page source
  — is built and verified on a live site.
