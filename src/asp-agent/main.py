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
from models import AgentPolicy, QuoteRequest, QuoteResponse

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
    Decide whether to buy this resource for the reader (script steps 28-30).

    Three outcomes, all of which the demo script requires be demonstrable:

      accept   -- at or below the auto-accept threshold, or the publisher has
                  come back at or under a price we previously countered with.
      counter  -- between the thresholds: propose a lower wholesale price.
      decline  -- above the ceiling: we will not authorise payment, and the
                  publisher shows the reader the step-29 refusal message.
    """
    policy = _policy()
    ask = Decimal(str(req.wholesalePrice))
    negotiation_id = req.negotiationId or f"neg-{secrets.token_hex(6)}"

    if ask > Decimal(str(policy.declineAbove)):
        logger.info(
            "quote %s: DECLINE %s at %s (above ceiling %s)",
            negotiation_id, req.resourceId, ask, policy.declineAbove,
        )
        return QuoteResponse(
            decision="decline",
            negotiationId=negotiation_id,
            reason=(
                f"{settings.home_base_name} does not authorise purchases above "
                f"${policy.declineAbove:.2f} for this reader."
            ),
        )

    if ask <= Decimal(str(policy.autoAcceptBelow)):
        retail = ask * Decimal(str(policy.markupRatio))
        logger.info(
            "quote %s: ACCEPT %s at %s (retail %s)",
            negotiation_id, req.resourceId, ask, retail,
        )
        await _log_agent_report(req, wholesale=ask, markup=policy.markupRatio)
        return QuoteResponse(
            decision="accept",
            negotiationId=negotiation_id,
            agreedPrice=_money(ask),
            retailPrice=_money(retail),
            reason=f"Authorised by {settings.home_base_name}.",
        )

    # Between the thresholds. If this is a continuing negotiation the publisher
    # has already seen our counter, so treat the return trip as agreement
    # rather than countering forever.
    if req.negotiationId:
        retail = ask * Decimal(str(policy.markupRatio))
        logger.info(
            "quote %s: ACCEPT on second pass %s at %s", negotiation_id, req.resourceId, ask
        )
        await _log_agent_report(req, wholesale=ask, markup=policy.markupRatio)
        return QuoteResponse(
            decision="accept",
            negotiationId=negotiation_id,
            agreedPrice=_money(ask),
            retailPrice=_money(retail),
            reason=f"Authorised by {settings.home_base_name} at the agreed price.",
        )

    counter = ask * Decimal(str(policy.counterFraction))
    logger.info(
        "quote %s: COUNTER %s at %s (asked %s)",
        negotiation_id, req.resourceId, counter, ask,
    )
    return QuoteResponse(
        decision="counter",
        negotiationId=negotiation_id,
        counterPrice=_money(counter),
        reason=(
            f"{settings.home_base_name} offers ${_money(counter):.4f} "
            f"for this resource."
        ),
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
