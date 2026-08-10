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

import logging
import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
from fastapi import FastAPI

from config import settings
from models import AgentPolicy, QuoteRequest, QuoteResponse  # noqa: F401

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

CENTS = Decimal("0.0001")


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


@app.post("/agent/quote", response_model=QuoteResponse)
async def quote(req: QuoteRequest) -> QuoteResponse:
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
