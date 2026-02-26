# Server Plan 05: Publisher WordPress Plugin

*Spec reference: Sections 2.1, 2.2, 3.3, 5.2, 7.2*

## Purpose

The WordPress plugin is the **primary publisher-side integration artifact** for the Missouri pilot. Given the prevalence of WordPress in independent news publishing, this plugin is how 3-5 Missouri newspapers will join the Newshare Network. It implements the OIDC Relying Party flow, maps the NetworkGroupId to local access controls, tags content with RSL metadata, and logs events to the ALS.

This is the piece that makes or breaks publisher adoption. It must be lightweight, non-disruptive to existing sites, and compatible with publishers' existing subscription/paywall systems.

## Core Responsibilities

- Implement OIDC Relying Party (RP) flow for "Network Login" button
- Receive and validate networkUserId + networkGroupId from ALS
- Map NetworkGroupId bitmask to local WordPress access controls
- Present "Network Login" option alongside existing local login
- Tag content with RSL (Really Simple Licensing) metadata
- Report events to ALS Logging Service (content access, ad views)
- Display retail price (wholesale pageClass × home base markupRatio) before purchase
- **Do NOT require publishers to abandon their existing subscriber systems**

## The "Allow Silos to Continue" Principle

The spec and governance documents emphasize that the Newshare Network is **additive, not a replacement**. A publisher joining the network is like a merchant accepting Visa — it doesn't prevent them from issuing their own store card. The plugin adds "Network Login" as an *option*, not a replacement for local accounts.

## Content Tagging: RSL Standard (from spec Section 3.3)

Publishers tag content with metadata for royalty computation and settlement:

| Content Attribute | Description |
|-------------------|-------------|
| `createdAt` | ISO 8601 timestamp |
| `expiresAt` | Optional expiration timestamp |
| `pubMbrId` | Publisher's network member ID (royalty recipient) |
| `doi` | Optional Digital Object Identifier |
| `rslTag` | Really Simple Licensing tag (rslstandard.org) |
| `pageClass` | Numeric wholesale royalty price |
| `markupRatio` | Retail markup ratio (supplied by user's home base in real time) |

RSL metadata is embedded in article HTML as JSON-LD.

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Platform** | WordPress plugin (PHP) | WordPress dominates independent news publishing |
| **OIDC Client** | PHP OIDC RP library (`jumbojett/openid-connect-php` or custom) | Standard OIDC Authorization Code Flow |
| **JWT Validation** | `firebase/php-jwt` | Validate tokens from ALS |
| **Content Tagging** | JSON-LD in article HTML | RSL metadata in `<script type="application/ld+json">` blocks |
| **Admin UI** | WordPress Settings API | Configuration page in WP admin |
| **Event Reporting** | HTTP POST to ALS Logging Service | Async event logging on content access |

## NetworkGroupId → Access Control Mapping

The plugin maps the bitmask to WordPress capabilities:

```php
// Example mapping configuration in WP Admin
$access_rules = [
    0    => 'meter',           // Anonymous: show N free articles
    2    => 'registered',      // Registered: show basic content
    4    => 'print_subscriber', // Print sub: full access
    8    => 'digital_sub',     // Digital sub: full access
    4096 => 'paid',            // Paid: full access
    8192 => 'trial',           // Trial: limited access
];

// Publisher configures which NetworkGroupId bits grant access to which content
// This preserves each publisher's unique access control model
```

## Plugin Configuration (WP Admin Screen)

```
Newshare Network Settings
─────────────────────────
Network Membership ID:     [pub_mbr_id]
ALS Auth Endpoint:         [https://als.newshare.example/auth]
ALS Logging Endpoint:      [https://als.newshare.example/log]
OIDC Client ID:            [auto-registered]
OIDC Client Secret:        [stored encrypted]

Content Pricing
───────────────
Default pageClass:         [0.05]  (wholesale price per article)
Premium pageClass:         [0.15]  (for premium/investigative content)

Access Control Mapping
──────────────────────
Anonymous (0):       [x] Show 3 free articles, then meter
Registered (2):      [x] Show all free content
Print Sub (4):       [x] Full access
Digital Sub (8):     [x] Full access
Paid (4096):         [x] Full access
Trial (8192):        [ ] Limited (first 5 articles)

RSL Tagging
───────────
Auto-tag new posts:  [x] Enabled
Default RSL license: [CC-BY-NC]
```

## Implementation Steps

### Phase 1: OIDC Integration (Weeks 1-4)
1. Build WordPress plugin skeleton (activation, deactivation, settings page)
2. Implement OIDC Relying Party flow:
   - "Log in with your news network" button on login page
   - Redirect to ALS Auth Service with required OIDC parameters
   - Handle callback: receive authorization code → exchange for tokens
   - Extract networkUserId, networkGroupId from ID Token claims
3. Implement NetworkGroupId → WordPress role/capability mapping
4. Build admin settings page for publisher configuration
5. Store network session alongside (not replacing) WordPress session
6. Implement session expiry and transparent re-authentication

### Phase 2: Content Tagging & Event Logging (Weeks 4-6)
7. Build RSL metadata injector: auto-insert JSON-LD in article `<head>`
8. Add pageClass field to WordPress post editor (custom meta box)
9. Implement event logging: POST to ALS on each content_access
10. Handle markupRatio display: show retail price when available from home base
11. Build content meter for anonymous users (configurable free article count)

### Phase 3: Publisher Pilot Deployment (Weeks 6-10)
12. Package plugin for WordPress.org-style distribution
13. Write installation/configuration guide for non-technical publishers
14. Deploy at 3-5 participating Missouri newspapers
15. Publisher-specific access control mapping configuration
16. Test full flow: user arrives from different home base → "Network Login" → content served
17. Verify events logged correctly to ALS
18. Iterate based on publisher feedback

## Infrastructure Requirements

- **No additional servers required** — plugin runs within publisher's existing WordPress installation
- **Outbound HTTPS** to ALS Auth and Logging endpoints
- **Minimal performance impact** — OIDC flow only triggers when user isn't locally authenticated
- **Compatibility:** WordPress 6.x, PHP 8.1+
- **Publisher integration support budget:** $15,000 (from funder brief) for small grants to participating newspapers for staff time

## Security Considerations

- OIDC client secret stored encrypted in WordPress options (not in wp-config.php plaintext)
- All OIDC flows over HTTPS with state parameter (CSRF protection)
- networkUserId stored as WordPress user meta (not in cookies)
- Plugin must NOT transmit user's local WordPress data to the network
- Event logging is fire-and-forget (async) — doesn't block page rendering
- Input validation on all ALS responses
- Plugin updates via standard WordPress update mechanism

## What the Plugin Does NOT Do

- Does NOT replace the publisher's existing login system
- Does NOT send user PII to the ALS or to other publishers
- Does NOT require publishers to change their CMS or content workflow
- Does NOT handle payment processing (that's ALS Settlement)
- Does NOT store content from other publishers

## Interfaces

- **ALS Auth Service** for OIDC authentication flow
- **ALS Logging Service** receives event logs (content_access, ad_view)
- **Home Base** (indirectly, via ALS) provides user's networkGroupId and markupRatio
- **Publisher's WordPress** integrates via standard WordPress plugin API
- **ITEGA Network Discovery** provides OIDC configuration endpoints
