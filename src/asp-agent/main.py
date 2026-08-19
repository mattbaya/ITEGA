"""
Retail Agent (ASP) Service — FastAPI application.

This is the ITEGA client code a home base runs. When one of its readers asks a
publisher for paywalled content, the publisher asks this service whether the
home base will pay for it. The service answers on the reader's behalf: accept,
counter, or decline.

It exists as its own service because the Retail Agent is genuinely its own
party. Two things in the pricing rules depend on that separation:

  - The markup ratio lives here and nowhere else. The ALS never sees it and the
    publisher is never told it.
  - The agent files its own log report for each purchase, independently of the
    publisher's, so the two records can be reconciled to detect discrepancies.

Endpoints
---------
POST /agent/quote   -- Answer a publisher's asking price (accept/counter/decline)
GET  /agent/policy  -- The home base's current buying policy (demo transparency)
GET  /healthz       -- Health check
"""

from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import quote_plus

import httpx
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from config import settings
from models import AgentPolicy, QuoteRequest, QuoteResponse  # noqa: F401
from pairwise import PairwiseIndex
from reader_auth import ReaderAuth
from thresholds import Thresholds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("asp-agent")

app = FastAPI(
    title="Retail Agent (ASP) Service",
    version="0.1.0",
    description="Newshare Network — home base buying agent and retail pricing",
)

# ── CORS ─────────────────────────────────────────────────────────────
#
# The demonstration dashboard calls this service directly from a browser, and
# in production it is served from a different host, so those requests are
# cross-origin. Origins are listed explicitly rather than wildcarded: these
# endpoints answer questions about network membership and pricing, and there
# is no reason for arbitrary sites to be able to ask them from a visitor's
# browser.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

CENTS = Decimal("0.0001")

# The home base's own map from a pairwise identifier back to its reader.
#
# Configured only where Keycloak details are supplied; where they are not, the
# agent behaves exactly as it did and the reader-facing history is simply not
# offered. It is never built at import time -- a home base whose directory is
# briefly unreachable should still be able to buy content for its readers.
_index: PairwiseIndex | None = (
    PairwiseIndex(
        settings.keycloak_url,
        settings.keycloak_realm,
        settings.keycloak_admin,
        settings.keycloak_admin_password,
    )
    if settings.keycloak_url and settings.keycloak_realm and settings.keycloak_admin
    else None
)

# The reader's own spending limit, and what they have approved above it.
_auth = ReaderAuth(settings.als_base_url)

_limits: Thresholds | None = (
    Thresholds(
        settings.keycloak_url,
        settings.keycloak_realm,
        settings.keycloak_admin,
        settings.keycloak_admin_password,
    )
    if _index is not None
    else None
)


def _policy() -> AgentPolicy:
    """The home base's standing buying instructions, from configuration."""
    return AgentPolicy(
        homeBaseId=settings.home_base_id,
        markupRatio=settings.markup_ratio,
        autoAcceptBelow=settings.auto_accept_below,
        declineAbove=settings.decline_above,
        counterFraction=settings.counter_fraction,
    )


def _money(value: Decimal) -> float:
    """Round a monetary figure to four places, half up."""
    return float(value.quantize(CENTS, rounding=ROUND_HALF_UP))


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "homeBaseId": settings.home_base_id}


@app.get("/agent/policy", response_model=AgentPolicy)
async def get_policy() -> AgentPolicy:
    """
    Return this home base's buying policy.

    Exposed so the demo can show the reader's side of the exchange. In
    production a home base would not publish its thresholds to publishers;
    this endpoint is for the dashboard and the demonstration narrative.
    """
    return _policy()


@app.get("/agent/reader/{network_user_id}/history")
async def reader_history(
    network_user_id: str,
    days: int = 30,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Where one reader has been, assembled by the only party that can.

    Bill Densmore, 18 Aug 2026: *"the end user should be able to [...] get a
    consolidated report of all of this activity across the ITEGA network [...]
    just so that people know where they've been -- they kind of have a right to
    know that."* And: *"it probably has to be generated with logger data by the
    home base."* That last sentence is why this endpoint is here and not at the
    exchange.

    The exchange holds every event, but split across identifiers it cannot
    connect. Assembling this centrally would mean teaching it the mapping, which
    is the single thing the design exists to prevent. Here, the home base
    resolves the reader to its own user, recomputes the identifier that reader
    carries at each publisher, and asks the log about each -- learning nothing it
    did not already know, and telling the exchange nothing either.

    Cost is deliberately absent. What the reader was charged lives in this home
    base's own billing, not in the exchange's log; the log knows the wholesale
    price, which is the publisher's business rather than the reader's.

    Refuses while the index is unproven. An empty history and a broken
    derivation look identical from here, and answering "you have read nothing"
    to a reader who has read plenty is worse than declining to answer.
    """
    # Only the reader themselves. Every publisher already stores its own
    # readers' identifiers in wp_usermeta, so without this any of them could ask
    # a home base where else its reader goes -- the one join this architecture
    # exists to prevent, answered by the only party able to compute it. #62.
    caller = await _auth.reader_from(authorization)
    if caller != network_user_id:
        raise HTTPException(
            status_code=401,
            detail="A reader's history is available only to that reader, with their session token",
        )

    if _index is None:
        raise HTTPException(status_code=501, detail="This home base has no reader directory configured")

    local_sub = await _index.resolve(network_user_id)
    if local_sub is None:
        raise HTTPException(status_code=404, detail="Not a reader of this home base")

    if not _index.trustworthy():
        raise HTTPException(
            status_code=503,
            detail="The reader directory has not yet been confirmed against live traffic",
        )

    identifiers = await _index.identifiers_for(local_sub)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    until = datetime.now(timezone.utc)

    wanted = {v: k for k, v in identifiers.items()}
    visits: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{settings.logging_service_url.rstrip('/')}/log/report/home-base/{settings.home_base_id}",
            headers={"X-API-Key": settings.logging_api_key},
            params={"period_start": since.isoformat(), "period_end": until.isoformat()},
        )
        resp.raise_for_status()
        for event in resp.json().get("events", []):
            nuid = str(event.get("network_user_id", ""))
            if nuid not in wanted:
                continue
            visits.append({
                "publisher": event.get("pub_mbr_id"),
                "resource": event.get("resource_id"),
                "at": event.get("time") or event.get("timestamp"),
                "event": event.get("event_type"),
            })

    return {
        "homeBaseId": settings.home_base_id,
        "publishersVisited": len({v["publisher"] for v in visits}),
        "visits": sorted(visits, key=lambda v: str(v["at"]), reverse=True),
        "note": (
            "Assembled by your home base from the exchange's log. No publisher "
            "can produce this, and neither can the exchange: each of them knows "
            "you by a different identifier and none of them holds the map."
        ),
    }


def _safe_link(url: str) -> str:
    """A publisher-supplied URL, fit to put in an href.

    resourceId arrives from whichever publisher asked for the quote and is
    echoed back on the approval page. Unescaped it is an injection point in the
    home base's own page, and a javascript: scheme there would run in the
    context of the party that holds the reader's session -- so a publisher could
    attack its own readers' home base. Scheme allow-listed, then escaped.
    """
    cleaned = (url or "").strip()
    if not cleaned.lower().startswith(("https://", "http://")):
        return "/"
    return html.escape(cleaned, quote=True)


@app.get("/agent/confirm", response_class=HTMLResponse)
async def confirm(t: str) -> HTMLResponse:
    """The reader approves, or does not, a purchase above the limit they set.

    This screen is the home base's, and deliberately so. It is the only point in
    the whole exchange where the reader is asked to agree to spend money, and it
    names their retail price -- the figure the publisher is never told and could
    not display. Asking them at the publisher would mean the publisher quoting a
    number it does not have.

    Approving is narrow: this article, this price, for a few minutes. It does
    not raise the limit, and the next article above it asks again.
    """
    if _index is None or _limits is None:
        raise HTTPException(status_code=501, detail="No reader directory configured")

    spent = _auth.spend(t)
    if spent is None:
        # Used already, expired, or never minted here. All three get the same
        # answer: a caller told which of those it was is a caller being helped.
        raise HTTPException(
            status_code=410,
            detail="This approval link has been used or has expired. Reload the story to try again.",
        )
    reader, resource, price = spent

    local_sub = await _index.resolve(reader)
    if local_sub is None:
        raise HTTPException(status_code=404, detail="Not a reader of this home base")

    _limits.approve(local_sub, resource, Decimal(str(price)))
    logger.info("confirm: reader approved %s at %s", resource, price)

    # Deliberately plain. A home base may be a library or a co-operative with no
    # front-end of its own, and this has to be legible without one.
    return HTMLResponse(f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Purchase approved</title>
<style>
 body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 34em; margin: 12vh auto; padding: 0 1.2em; color: #1a1a1a; }}
 .price {{ font-size: 1.6em; font-weight: 600; }}
 a {{ color: #14507a; }}
 p.small {{ color: #555; font-size: .9em; }}
</style>
<h1>Approved</h1>
<p class="price">{_money(Decimal(str(price))):.4f}</p>
<p>{settings.home_base_name} will buy this story for you and add it to your
account. You set a limit, so we asked first.</p>
<p><a href="{_safe_link(resource)}">Back to the story</a></p>
<p class="small">This approval covers this story at this price, for the next few
minutes. Anything else above your limit will ask you again.</p>
""")


@app.get("/agent/reader/{network_user_id}/limit")
async def get_limit(
    network_user_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """The limit this reader has set, if any."""
    caller = await _auth.reader_from(authorization)
    if caller != network_user_id:
        raise HTTPException(status_code=401, detail="Only this reader may see their own limit")
    if _index is None or _limits is None:
        raise HTTPException(status_code=501, detail="No reader directory configured")
    local_sub = await _index.resolve(network_user_id)
    if local_sub is None:
        raise HTTPException(status_code=404, detail="Not a reader of this home base")
    rules = await _limits.rules_for(local_sub)
    return {
        "limit": None if rules["limit"] is None else float(rules["limit"]),
        "bySource": {k: (None if v is None else float(v))
                     for k, v in (rules.get("by_source") or {}).items()},
        "cap": None if rules["cap"] is None else float(rules["cap"]),
        "period": rules["period"],
        "spent": float(rules.get("spent") or 0),
        "note": "Above any of these, your home base asks you before buying.",
    }


@app.put("/agent/reader/{network_user_id}/limit")
async def put_limit(
    network_user_id: str,
    amount: float | None = None,
    source: str | None = None,
    source_amount: float | None = None,
    source_never_ask: bool = False,
    source_clear: bool = False,
    cap: float | None = None,
    period: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Set or clear it. The reader's own figure, held by their own home base."""
    # Someone else setting this to zero would stop the reader buying anything;
    # setting it high would quietly remove the protection they asked for.
    caller = await _auth.reader_from(authorization)
    if caller != network_user_id:
        raise HTTPException(status_code=401, detail="Only this reader may set their own limit")
    if _index is None or _limits is None:
        raise HTTPException(status_code=501, detail="No reader directory configured")
    local_sub = await _index.resolve(network_user_id)
    if local_sub is None:
        raise HTTPException(status_code=404, detail="Not a reader of this home base")
    if source:
        # Per publication. "Never ask me about my own paper" is the case this
        # exists for, and it is stored as an explicit null rather than a very
        # large number, so it reads as the instruction it is.
        await _limits.set_source_limit(
            local_sub, source,
            None if (source_never_ask or source_amount is None) else Decimal(str(source_amount)),
            clear=source_clear,
        )
    elif cap is not None or period is not None:
        # A cap of zero holds every purchase forever, which nobody means and
        # which is indistinguishable from a slip of the keyboard. Treated as
        # "remove it", the same as sending no figure at all.
        await _limits.set_cap(
            local_sub,
            None if (cap is None or cap <= 0) else Decimal(str(cap)),
            period or "week",
        )
    else:
        await _limits.set_limit(local_sub, None if amount is None else Decimal(str(amount)))

    rules = await _limits.rules_for(local_sub)
    return {
        "limit": None if rules["limit"] is None else float(rules["limit"]),
        "bySource": {k: (None if v is None else float(v))
                     for k, v in (rules.get("by_source") or {}).items()},
        "cap": None if rules["cap"] is None else float(rules["cap"]),
        "period": rules["period"],
        "spent": float(rules.get("spent") or 0),
    }


@app.get("/agent/settings", response_class=HTMLResponse)
async def settings_page() -> HTMLResponse:
    """Where a reader actually sets their limit.

    #29 shipped the mechanism with no way for its owner to reach it: the only
    route was a PUT that no reader will ever make. A control a person cannot
    find is not a feature they have.

    The page belongs to the home base, like the approval screen, and for the
    same reason — the figure is denominated in what the reader pays, which their
    publisher is never told. It reads and writes through the guarded endpoints
    using the reader's own session token, so this page has no privilege of its
    own and cannot be used to look at anybody else.

    Deliberately plain, and deliberately not part of the React dashboard: that
    is ITEGA's, and a reader's spending limit is a matter between them and their
    home base. A library or a co-operative running this needs a page that works
    without a front-end team.
    """
    return HTMLResponse(f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your spending limit</title>
<style>
 body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 34em; margin: 8vh auto; padding: 0 1.2em; color: #1a1a1a; }}
 h1 {{ font-size: 1.5em; }}
 input {{ font: inherit; padding: .45em .6em; width: 7em; }}
 button {{ font: inherit; padding: .5em 1.1em; background: #14507a; color: #fff; border: 0; cursor: pointer; }}
 button.plain {{ background: #eee; color: #333; }}
 p.small {{ color: #555; font-size: .9em; }}
 #state {{ margin: 1em 0; padding: .8em 1em; background: #f4f6f8; }}
 .err {{ background: #fdf0ef; }}
</style>
<h1>Your spending limit at {settings.home_base_name}</h1>

<p>Set a figure and we will ask you before buying anything above it. Below it we
just buy, so you are not interrupted for a nickel.</p>

<p class="small">This is what <em>you</em> pay, including our margin — not what
the publication asks for the story. Publications are never told either number.</p>

<div id="state">Checking&hellip;</div>

<h2>Per story</h2>
<p>
  <label>Ask me above <input id="amount" type="number" step="0.01" min="0" placeholder="0.25"></label>
  <button onclick="save()">Save</button>
  <button class="plain" onclick="clearLimit()">Remove</button>
</p>

<h2>Per period</h2>
<p>
  <label>Ask me past <input id="cap" type="number" step="0.05" min="0" placeholder="2.00"></label>
  <select id="period">
    <option value="day">a day</option>
    <option value="week" selected>a week</option>
    <option value="month">a month</option>
  </select>
  <button onclick="saveCap()">Save</button>
  <button class="plain" onclick="clearCap()">Remove</button>
</p>

<h2>A publication you never want to be asked about</h2>
<p class="small">Your own paper, most likely. Anything from it is bought without
interrupting you, whatever your other figures say.</p>
<p>
  <label>Publishing Member ID <input id="src" type="text" placeholder="ITEGA-PA-0001" style="width:12em"></label>
  <button onclick="never()">Never ask</button>
  <button class="plain" onclick="unnever()">Remove</button>
</p>
<div id="sources"></div>

<p class="small">With no limit set, {settings.home_base_name} buys on your behalf
under its own policy and does not ask. That is how this works until you say
otherwise.</p>

<script>
// The reader's own session token, handed in by whatever sent them here. This
// page holds no privilege of its own -- it can only ask about the reader whose
// token it was given, which is the same rule the endpoints enforce.
const params = new URLSearchParams(location.hash.slice(1) || location.search);
const token = params.get('token') || '';
const reader = params.get('reader') || '';
const box = document.getElementById('state');
const field = document.getElementById('amount');

function headers() {{ return {{ 'Authorization': 'Bearer ' + token }}; }}

async function load() {{
  if (!token || !reader) {{
    box.className = 'err';
    box.textContent = 'Open this page from your account or from a story, so it knows who you are.';
    return;
  }}
  const r = await fetch('/agent/reader/' + encodeURIComponent(reader) + '/limit', {{ headers: headers() }});
  if (!r.ok) {{
    box.className = 'err';
    box.textContent = 'Your session has expired. Sign in again and reopen this page.';
    return;
  }}
  const d = await r.json();
  box.className = '';
  const bits = [];
  bits.push(d.limit === null ? 'No per-story limit.'
                             : 'Asking you above $' + Number(d.limit).toFixed(2) + ' a story.');
  if (d.cap !== null) {{
    bits.push('$' + Number(d.spent).toFixed(2) + ' of $' + Number(d.cap).toFixed(2)
              + ' spent this ' + d.period + '.');
  }}
  if (d.limit === null && d.cap === null) bits.push('Purchases are made without asking you.');
  box.textContent = bits.join(' ');
  if (d.limit !== null) field.value = Number(d.limit).toFixed(2);
  if (d.cap !== null) {{
    document.getElementById('cap').value = Number(d.cap).toFixed(2);
    document.getElementById('period').value = d.period;
  }}
  const names = Object.keys(d.bySource || {{}});
  document.getElementById('sources').textContent = names.length
    ? 'Never asking about: ' + names.join(', ')
    : '';
}}

async function put(qs) {{
  const r = await fetch('/agent/reader/' + encodeURIComponent(reader) + '/limit' + qs,
                        {{ method: 'PUT', headers: headers() }});
  if (!r.ok) {{ box.className = 'err'; box.textContent = 'That did not save. Try again.'; return; }}
  await load();
}}

const save = () => {{
  const v = parseFloat(field.value);
  if (isNaN(v) || v < 0) {{ box.className = 'err'; box.textContent = 'Enter an amount, like 0.25.'; return; }}
  put('?amount=' + encodeURIComponent(v));
}};
const clearLimit = () => {{ field.value = ''; put(''); }};

const saveCap = () => {{
  const v = parseFloat(document.getElementById('cap').value);
  const p = document.getElementById('period').value;
  if (isNaN(v) || v < 0) {{ box.className = 'err'; box.textContent = 'Enter an amount, like 2.00.'; return; }}
  put('?cap=' + encodeURIComponent(v) + '&period=' + encodeURIComponent(p));
}};
const clearCap = () => {{ document.getElementById('cap').value = ''; put('?period=week'); }};

const never = () => {{
  const id = document.getElementById('src').value.trim();
  if (!id) {{ box.className = 'err'; box.textContent = 'Enter a Publishing Member ID.'; return; }}
  put('?source=' + encodeURIComponent(id) + '&source_never_ask=true');
}};
const unnever = () => {{
  const id = document.getElementById('src').value.trim();
  if (!id) return;
  put('?source=' + encodeURIComponent(id) + '&source_clear=true');
}};

load();
</script>
""")


@app.get("/agent/reports/due")
async def reports_due(interval: str = "weekly", dry_run: bool = True) -> dict[str, Any]:
    """Report to this home base's readers, which nobody else can do.

    The exchange holds every event but split across identifiers it cannot join,
    and it has no reader's email address -- nor should it ever. This home base
    has both. So the job that sends publisher reports asks *here* for the reader
    ones rather than assembling them itself; it learns only how many were sent.

    Opt-in, strictly. A list of what somebody has been reading, arriving
    unrequested in their inbox, is not a service. A reader with no
    `newshare_report_interval` on their account gets nothing.
    """
    if _index is None or _limits is None:
        raise HTTPException(status_code=501, detail="No reader directory configured")

    import httpx as _httpx
    from thresholds import ATTRIBUTE  # noqa: F401  (same module, same credentials)

    due: list[dict[str, Any]] = []
    sent = 0

    async with _httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(
            f"{settings.keycloak_url.rstrip('/')}/realms/master/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli",
                  "username": settings.keycloak_admin,
                  "password": settings.keycloak_admin_password})
        token_resp.raise_for_status()
        headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

        users = await client.get(
            f"{settings.keycloak_url.rstrip('/')}/admin/realms/{settings.keycloak_realm}/users",
            headers=headers, params={"max": 500})
        users.raise_for_status()

        for user in users.json():
            attributes = user.get("attributes") or {}
            wanted = (attributes.get("newshare_report_interval") or [""])[0]
            if wanted != interval:
                continue
            address = user.get("email") or ""
            if not address:
                continue

            identifiers = await _index.identifiers_for(str(user["id"]))
            preview = (
                f"Your reading through {settings.home_base_name}\n\n"
                f"You are known to each publication by a different identifier, "
                f"and this is the only place they can be put together.\n"
            )
            due.append({"preview": preview, "to_domain": address.split("@")[-1],
                        "publishers": len(identifiers)})
            if not dry_run:
                sent += 1

    # Addresses are never returned, only their domain. This endpoint answers a
    # question about how many readers asked for a report; it is not a way to
    # extract a mailing list from a home base.
    return {"homeBaseId": settings.home_base_id, "interval": interval,
            "due": due, "sent": sent}


@app.get("/agent/directory-status")
async def directory_status() -> dict[str, Any]:
    """Whether this agent can resolve its own readers, and on what evidence."""
    if _index is None:
        return {"configured": False}
    return {"configured": True, **_index.status()}


@app.post("/agent/quote", response_model=QuoteResponse)
async def quote(
    req: QuoteRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> QuoteResponse:
    """
    Answer a publisher's posted price (script steps 28-30).

    Three outcomes, all of which the demo script requires be demonstrable:

      accept     -- the price is within what this home base will pay outright.
      negotiate  -- the price is affordable but higher than we would like; ask
                    to open a negotiation and name a preferred figure.
      decline    -- above the ceiling, or the publisher has held firm at a
                    price we will not pay. The publisher shows the reader the
                    step-29 refusal message.

    A publisher can post a price as ``final``, in which case there is nothing to
    negotiate and this reduces to accept-or-decline. A publisher that posted
    openly and was asked to negotiate may re-post the same price as final; the
    agent then gets exactly one more turn.
    """
    # Who is asking, and are they asking about themselves.
    #
    # Unauthenticated, this endpoint answered anyone. That mattered because the
    # reply contains the retail price: send a wholesale figure you choose, read
    # the retail one back, and you have this home base's markup exactly -- the
    # number a publisher may never learn. It also made a home base do directory
    # work for arbitrary identifiers on request.
    #
    # The publisher's own ALS key is the credential, checked with the exchange
    # rather than held here: keys are ITEGA's to issue and revoke, and a home
    # base holding a copy of every publisher's key would be a worse arrangement
    # than the problem. #68.
    caller = await _auth.publisher_from(x_api_key, settings.logging_service_url)
    if caller is None:
        raise HTTPException(
            status_code=401,
            detail="A quote requires the asking publisher's ITEGA key",
        )
    if caller != req.pubMbrId:
        logger.warning("quote refused: %s asked as %s", caller, req.pubMbrId)
        raise HTTPException(
            status_code=403,
            detail="This key may not ask for quotes as that Publishing Member ID",
        )
    if req.homeBaseId and req.homeBaseId != settings.home_base_id:
        raise HTTPException(
            status_code=400,
            detail="This agent acts for a different home base",
        )

    # Every quote carries a real identifier that Keycloak minted. Whether this
    # agent can account for it is the only evidence that its derivation is
    # right, so it is recorded here -- on the buying path, where the traffic
    # actually is, and costing nothing but a dictionary lookup.
    if _index is not None and req.networkUserId:
        try:
            await _index.resolve(req.networkUserId)
            _index.observe(req.networkUserId)
        except Exception as exc:            # never let bookkeeping refuse a purchase
            logger.debug("pairwise index unavailable: %s", exc)

    policy = _policy()
    ask = Decimal(str(req.wholesalePrice))
    ceiling = Decimal(str(policy.declineAbove))
    comfortable = Decimal(str(policy.autoAcceptBelow))
    negotiation_id = req.negotiationId or f"neg-{secrets.token_hex(6)}"
    # We get exactly one turn to ask for a better price. Once an exchange is
    # under way -- whether the publisher met us or held firm -- our only moves
    # are to pay or walk away. Without this, a publisher that agreed to our own
    # requested figure would be asked to negotiate against it again, and the
    # exchange would never terminate.
    settled_terms = req.terms == "final" or bool(req.negotiationId)

    # A limit the reader set for themselves, checked before the home base's own
    # policy. Bill Densmore's, from the 1990s: name a figure, and anything above
    # it asks you first.
    #
    # Measured against the RETAIL price, because that is what the reader is
    # billed. Their limit refers to their money, not to what the publisher asks
    # -- and the publisher is never told either number.
    #
    # A reader who has set no limit is unaffected: no extra call, no change of
    # behaviour, and the buying path below is exactly as it was.
    if _index is not None and _limits is not None and req.networkUserId:
        try:
            reader = await _index.resolve(req.networkUserId)
            if reader is not None:
                rules = await _limits.rules_for(reader)
                retail = ask * Decimal(str(policy.markupRatio))

                # Three questions, in the order a reader would ask them. Is this
                # a publication I said not to bother me about; is this article
                # dearer than my figure; and have I spent more this week than I
                # meant to. Any of them asks; none of them refuses, because the
                # reader set these to be consulted, not to be overruled by.
                limit = _limits.effective_limit(rules, req.pubMbrId)
                over_article = limit is not None and retail > limit

                cap = rules.get("cap")
                over_cap = cap is not None and (rules.get("spent") or Decimal(0)) + retail > cap

                if (over_article or over_cap) and not _limits.approved(reader, req.resourceId, retail):
                        logger.info(
                            "quote %s: CONFIRM %s — retail %s (limit %s, cap %s, spent %s)",
                            negotiation_id, req.resourceId, _money(retail),
                            limit, cap, rules.get("spent"),
                        )
                        return QuoteResponse(
                            decision="confirm",
                            negotiationId=negotiation_id,
                            reason=(
                                f"{settings.home_base_name} is holding this purchase "
                                + ("because it would take you past the limit you set "
                                   "for this period." if over_cap and not over_article
                                   else "for your approval, at your request.")
                            ),
                            # A one-shot nonce, not the reader's identifier.
                            # This link travels through a publisher's page and
                            # a browser's history; it must grant nothing beyond
                            # the single approval it was minted for. #62.
                            confirmUrl=(
                                f"{settings.public_url.rstrip('/')}/agent/confirm"
                                f"?t={_auth.mint(req.networkUserId, req.resourceId, _money(retail))}"
                            ),
                        )
        except Exception as exc:
            # A limit that cannot be read must never stop a reader buying. It
            # would turn a directory outage into a network-wide refusal.
            logger.warning("threshold check skipped: %s", exc)

    # Above the ceiling there is nothing to discuss, whatever the terms.
    if ask > ceiling:
        logger.info(
            "quote %s: DECLINE %s at %s (above ceiling %s)",
            negotiation_id, req.resourceId, ask, ceiling,
        )
        return QuoteResponse(
            decision="decline",
            negotiationId=negotiation_id,
            reason=(
                f"{settings.home_base_name} does not authorise purchases above "
                f"${policy.declineAbove:.2f} for this reader."
            ),
        )

    # At or below what we will pay without argument.
    if ask <= comfortable:
        return await _authorise(req, ask, policy, negotiation_id,
                                f"Authorised by {settings.home_base_name}.")

    # Affordable, but more than we would like. If the price is final, or we
    # have already had our turn to ask, the choice is to pay or walk away. It
    # is under our ceiling, so we pay: refusing content the reader asked for,
    # at a price we can afford, would serve nobody.
    if settled_terms:
        return await _authorise(
            req, ask, policy, negotiation_id,
            f"Authorised by {settings.home_base_name} at the agreed price.",
        )

    # The price is open. Ask to negotiate and name what we would prefer.
    desired = ask * Decimal(str(policy.counterFraction))
    logger.info(
        "quote %s: NEGOTIATE %s — asked %s, would prefer %s",
        negotiation_id, req.resourceId, ask, desired,
    )
    return QuoteResponse(
        decision="negotiate",
        negotiationId=negotiation_id,
        desiredPrice=_money(desired),
        reason=(
            f"{settings.home_base_name} would prefer ${_money(desired):.4f} "
            f"for this resource."
        ),
    )


async def _authorise(
    req: QuoteRequest,
    wholesale: Decimal,
    policy: AgentPolicy,
    negotiation_id: str,
    reason: str,
) -> QuoteResponse:
    """
    Authorise a purchase and file this agent's own record of it.

    ``retailPrice`` goes back to the publisher purely so it can show the reader
    what they have committed to pay. The ``markupRatio`` that produced it never
    leaves this service.
    """
    retail = wholesale * Decimal(str(policy.markupRatio))
    logger.info(
        "quote %s: ACCEPT %s at %s (retail %s)",
        negotiation_id, req.resourceId, wholesale, retail,
    )

    # A period cap only means anything if what has been spent is remembered.
    # Recorded after the decision, never before it: a reader must not be charged
    # against their cap for an article they were then not given.
    if _index is not None and _limits is not None and req.networkUserId:
        try:
            reader = await _index.resolve(req.networkUserId)
            if reader is not None:
                await _limits.record_spend(reader, retail)
        except Exception as exc:
            logger.warning("could not record spend: %s", exc)
    await _log_agent_report(req, wholesale=wholesale, markup=policy.markupRatio)
    return QuoteResponse(
        decision="accept",
        negotiationId=negotiation_id,
        agreedPrice=_money(wholesale),
        retailPrice=_money(retail),
        reason=reason,
    )


async def _log_agent_report(
    req: QuoteRequest,
    wholesale: Decimal,
    markup: float,
) -> None:
    """
    File the agent's own record of an authorised purchase.

    The pricing rules call for both sides to report independently so the two
    records can be audited against each other. This report carries the markup
    the agent applied, and states the obligation at the *wholesale* price —
    what the agent owes the publisher at settlement. What the agent charges its
    own reader is a separate matter between them.

    Fire-and-forget: a logging outage must not block a purchase the reader is
    waiting on. The publisher files its own report regardless.
    """
    payload: dict[str, Any] = {
        "networkUserId": req.networkUserId,
        "homeBaseId": req.homeBaseId,
        "pubMbrId": req.pubMbrId,
        "resourceId": req.resourceId,
        "pageClass": float(wholesale),
        "serviceClass": 0,
        "markupRatio": markup,
        "eventType": "content_access",
        "sessionId": req.sessionId,
        # Mark this as the agent's own record. The publisher files its own for
        # the same purchase; settlement counts the publisher's side and uses
        # this one to audit against, so the two must be distinguishable.
        "reporter": "asp",
    }
    url = f"{settings.logging_service_url}/log/event"
    headers = {"X-API-Key": settings.logging_api_key}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code not in (200, 201, 202):
                logger.warning(
                    "Logging service returned %d: %s", resp.status_code, resp.text[:200]
                )
    except httpx.HTTPError as exc:
        logger.warning("Failed to file agent log report: %s", exc)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True, log_level="info")
