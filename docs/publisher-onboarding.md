# Onboarding a publisher

*How a real newspaper joins the network, and what ITEGA has to do first.*

No credentials appear here; this repository is public.

---

## The shape of it

**A publisher installs the plugin and activates it. That is their whole job.**
No Publishing Member ID typed in, no API key pasted into a settings form, no
support call. Everything else is decided in advance by ITEGA and fetched by the
plugin.

That is only possible because the plugin ships with no secrets in it — which it
must not, being a public download at `dashboard.itega.org/plugin/`.

## What ITEGA does first

Register the publisher's domains in the provisioning store. **This is the
certification step**: in a real network it is where the paperwork, the banking
details and the governance sit, and being in that file is what ITEGA decided,
not what a plugin asked for.

The store lives at `infra/vps2/data/provisioning.json` on VPS 2 — mode 600,
gitignored, and deliberately **not** `registry.json`, which is served to anyone
who asks at `/discovery/publishers`. One holds public directory entries; this
one holds keys.

```json
{
  "domains": {
    "example.org": {
      "name": "Example Publisher",
      "pub_mbr_id": "ITEGA-XX-0000",
      "api_key": "...",
      "demo_key": "example-a1b2c3d4",
      "revoked": false
    }
  }
}
```

A publisher with more than one property gets one entry per domain. They may
share a member ID, so settlement totals to one member, or hold separate ones.

There is `provisioning.json.example` in the repository with the shape and the
generator command.

## What the plugin does

1. Publishes a random nonce at `/.well-known/newshare-challenge`
2. `POST https://network.itega.org/provision` with `{domain, nonce}`
3. The discovery service fetches that URL and compares the body
4. On success: Publishing Member ID, per-publisher API key, service endpoints,
   demonstration key

Scheduled a few seconds after activation rather than run inline, because
activation happens during the plugin-upload request and this call waits on the
exchange fetching a URL back from the site.

## Why the domain has to be proved

An endpoint answering *"what are the credentials for example.org?"* cannot tell
a plugin from a stranger. The domain arrives as a parameter, and **a parameter
is a claim, not proof**. Without a check, anyone who knew a member's domain —
public information, listed at `/discovery/publishers` — could ask for its key.

So the caller proves it. This is ACME's HTTP-01 challenge, chosen for the
reason Let's Encrypt chose it: it is the cheapest check that cannot be faked by
someone who does not run the site.

`verify_domain()` is deliberately strict, and each rule is load-bearing:

- **HTTPS only.** Plain HTTP is spoofable by anyone on the path.
- **No redirects followed.** Otherwise "example.org redirects to
  attacker.example" would prove the attacker controls example.org.
- **Exact match on a size-capped body.** A page that merely *contains* the
  nonce does not pass.
- **Minimum nonce length.** A short or empty nonce never verifies, whatever
  comes back.

An earlier design used a one-time claim instead — first activation wins. That
is weaker (it only makes theft a race) and worse operationally, because a
reinstall then needs an operator to unlock the entry. Verification re-proves
control every time, so reinstalling simply works.

### What it does not defend against

Someone who already controls the publisher's web server. That is the same
assumption every certificate authority makes, and if it is false the publisher
has larger problems than this key.

## Per-publisher keys

Each publisher gets its own API key, and **a key may only file events under its
own Publishing Member ID**.

This is not decoration. `pubMbrId` arrives in the request body of
`POST /log/event`. With one shared key — which is how this started — any holder
could file settlement-affecting reads attributed to any publisher: crediting
themselves, or loading a competitor with traffic they never had. The key now
decides who you are allowed to say you are.

The internal key (`ALS_API_KEY`) still acts for every publisher, because the
Auth Service files authentication events on their behalf and settlement reads
across all of them.

Verified live:

| Presented | Filing as | Result |
|---|---|---|
| wesmc's key | `ITEGA-WESMC-0003` | **202** |
| wesmc's key | `ITEGA-PA-0001` | **403** |
| an invented key | anything | **403** |

## Operating it

**Register a domain.** Add an entry to the store and restart
`network-discovery`. Generate the key with
`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.

**Stop issuing for a domain.** Set `"revoked": true`. The record and its audit
trail survive; verification alone would otherwise keep admitting the current
owner.

**See who has provisioned.** Each entry carries an `issued` list of timestamps
and source addresses, capped at the last 20.

**Re-certify a site from scratch** — the useful end-to-end test:

```bash
wp option delete newshare_pub_mbr_id newshare_als_api_key newshare_demo_key
wp eval '$r = Newshare_Provisioning::provision(); echo $r["message"], "\n";'
```

Done against wesmc.org: it reconfigured in one call and passed all 18 journey
checks afterwards.

## Two failures worth not repeating

**`os.replace` onto a bind-mounted *file* returns `EBUSY`.** Docker makes the
file itself a mount point, so the atomic write-and-rename that protects the
store from a truncating crash fails. It failed *after* the domain had verified,
which made it look like a verification bug. The compose file mounts the
**directory** now, and `_save()` keeps an in-place fallback.

**FastAPI exports its own `Path`.** Importing `pathlib.Path` alongside it in
`als-logging` silently shadowed one with the other. The container started,
`/healthz` returned 200, and every authenticated request returned 500 —
including ones that should have been a clean 403. Import it as `FilePath`, as
`network-discovery` already did.

Both are the recurring shape in this project: **a check that cannot observe
what it claims to.** A health endpoint that answers 200 while every real
request fails is not a health check.

## Registered today

| Domain | Member ID | Status |
|---|---|---|
| `barharbor.info` | `ITEGA-PA-0001` | provisioned |
| `northberkshire.org` | `ITEGA-PB-0001` | registered |
| `wesmc.org` | `ITEGA-WESMC-0003` | provisioned |
| `greylockglass.com` | `ITEGA-GG-0001` | registered, awaiting install |
| `greylockguardian.com` | `ITEGA-GG-0002` | registered, awaiting install |

Greylock Glass is the first real newspaper, hosting this as a favour, on the
condition that it never affects its ordinary readers. Demo mode is what keeps
that promise; see `src/wordpress-plugin/README.md`.
