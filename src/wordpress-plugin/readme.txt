=== Newshare Network ===
Contributors: itega
Tags: federated-identity, sso, oidc, paywall, news-network
Requires at least: 6.0
Tested up to: 6.7
Requires PHP: 8.1
Stable tag: 0.2.5
License: GPL-2.0-or-later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Federated identity and content access for the Newshare Network. Adds cross-publisher SSO with privacy-preserving pseudonymous identifiers.

== Description ==

The Newshare Network plugin integrates your WordPress site with the Newshare Network, a four-party federated identity system for news publishers.

**What it does:**

* Adds a "Network Login" option alongside your existing login form
* Validates user sessions via the ALS (Account Ledger Service)
* Controls content access based on subscription tiers using bitmask logic
* Tags content with RSL (Resource Specification Language) metadata
* Logs content access events to the ALS for settlement

**Privacy by design:**

* No PII is sent to the network — only opaque pseudonymous identifiers
* The plugin does not replace your existing login system — it is additive
* Auth state uses tokens, not cookies (the WP session itself uses standard WP cookies)
* Network users are created as WordPress subscribers with no personal information

**Architecture:**

The OIDC authentication flow goes through the ALS, not directly to Keycloak. The plugin acts as a Relying Party in the federated identity system.

== Installation ==

1. Upload the `newshare-network` folder to `/wp-content/plugins/`
2. Install Composer dependencies:

    cd /wp-content/plugins/newshare-network
    composer install --no-dev --optimize-autoloader

3. Activate the plugin through the Plugins menu in WordPress
4. Go to Settings > Newshare Network to configure:
   - Your Publisher Member ID (provided by the network)
   - ALS Auth and Logging endpoint URLs
   - API key for the logging service
   - Default content pricing and access tier settings

5. Use the "Test Connection" button to verify your configuration

== Configuration ==

= Network Identity =
* **Publisher Member ID** — Your unique identifier in the Newshare Network (e.g., PUB003)

= ALS Endpoints =
* **ALS Auth URL** — The ALS authentication endpoint
* **ALS Logging URL** — The ALS event logging endpoint
* **ALS API Key** — Your API key for the logging service
* **ALS JWKS URL** — Optional override for the token validation key endpoint

= Content Pricing =
* **Default Page Class** — Default wholesale price for content (default: 0.05)
* **Premium Page Class** — Wholesale price for premium content (default: 0.15)

= Access Control =
* **Default Access Tier** — Default subscription tier required (default: Free)
* **Free Article Meter** — Number of gated articles anonymous visitors can read (default: 3)

= RSL Defaults =
* **Default RSL Tag** — Default content license tag (default: CC-BY-NC)

== Per-Post Settings ==

Each post has a "Newshare Access Control" meta box in the editor with:

* **Required Access Tier** — Override the site-wide default for this post
* **Page Class** — Override the wholesale price for this post
* **RSL Tag** — Override the license tag for this post

== Access Tiers ==

The network uses bitmask values for subscription tiers:

* 0 — Free (no login required)
* 2 — Registered (logged in, any tier)
* 4 — Print Subscriber
* 8 — Digital Subscriber
* 4096 — Paid Subscriber
* 8192 — Trial

Access is checked via bitwise AND: users must have all required bits set.

== Frequently Asked Questions ==

= Does this replace my existing login system? =

No. The Newshare Network login is additive. Your existing users, roles, and login form continue to work exactly as before. The plugin adds a "Network Login" option alongside the standard form.

= What data is shared with the network? =

Only opaque identifiers — no personally identifiable information. The network uses pseudonymous user IDs and session tokens. Content access events are logged with publisher IDs and resource URLs, but never with user emails, names, or IP addresses.

= Do I need Keycloak? =

No. The plugin communicates with the ALS (Account Ledger Service), which handles the Keycloak interaction on behalf of the network. Your plugin never talks to Keycloak directly.

== Changelog ==

= 0.2.5 =
* The gate no longer presents the publisher's asking price as the reader's price
* Reader-facing copy rewritten in the reader's order of asking, and left-aligned
* A home base may be a library or cooperative, not only a newspaper

= 0.2.4 =
* A site left live for all readers can be put back to demonstration only

= 0.2.3 =
* The publisher's own signed-in readers are never gated, metered or quoted

= 0.2.2 =
* The access gate names what the article costs

= 0.2.1 =
* Updates arrive through WordPress's own update machinery
* Demo mode is no longer a setting; the plugin is a demonstration throughout
* US spellings in reader-facing copy

= 0.2.0 =
* Self-provisioning: the plugin fetches its own credentials, proving it controls
  the domain by serving a nonce the discovery service fetches back over HTTPS
* Network readers get their own role, "ITEGA Guest", holding read and nothing else
* A status indicator tells a reader whether they are signed in to the network
* No assets are loaded at all when demo mode is suppressing the plugin

= 0.1.0 =
* Initial release
* OIDC Relying Party flow through the ALS
* Content access control with bitmask subscription tiers
* RSL JSON-LD metadata injection
* Content access event logging
* Anonymous article meter
* WordPress Settings API integration
* Post editor meta box for per-post access control
