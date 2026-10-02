"""The quote endpoint, which is FR-05.

Public by declaration. A visitor sees what a hire will cost before there is
any account, and before reserving anything (US-11).

The router does no arithmetic. It reads the query string, hands it to the
quote service and writes out the figures the pricing policy returned. No
amount is added, multiplied or rounded here.

The period is half open and is held to the same limits as the availability
routes, so a quote is never given for a hire that could not then be booked.

No trade discount is applied on this route. The route is public, so it does
not know who is asking. The dependencies that read an account are the role
policies, and a route that is public and depends on one of them as well is
refused at start-up. Reading the account some other way would step around that
check, so this route does not. The quote service takes the discount as an
input, and the booking flow, which knows the customer, passes it.

The answer is never cached. A rate can change, and a quote that was kept would
then show a price nobody is offering.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.catalogue_deps import FromDate, ToDate, never_cache
from app.api.catalogue_schemas import (
    BASIS_TO_WIRE,
    REFUSED_QUERY_RESPONSE,
    UNKNOWN_MODEL_RESPONSE,
    QuoteResponse,
    UnitQuoteResponse,
)
from app.api.deps import public_access
from app.api.pricing_deps import QuoteHireDependency
from app.api.schemas import MAXIMUM_QUANTITY, MINIMUM_QUANTITY
from app.application.money.quote import ModelQuote

router = APIRouter(
    prefix="/catalogue", tags=["pricing"], dependencies=[Depends(public_access)]
)


@router.get(
    "/models/{slug}/quote",
    response_model=QuoteResponse,
    summary="Return what a hire of one model will cost",
    dependencies=[Depends(never_cache)],
    responses={
        status.HTTP_404_NOT_FOUND: UNKNOWN_MODEL_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_model_quote(
    slug: str,
    from_date: FromDate,
    to_date: ToDate,
    quotes: QuoteHireDependency,
    quantity: Annotated[
        int,
        Query(
            ge=MINIMUM_QUANTITY,
            le=MAXIMUM_QUANTITY,
            description="How many units are wanted.",
        ),
    ] = MINIMUM_QUANTITY,
) -> QuoteResponse:
    """Return the price of hiring `quantity` units of one model for the period.

    Raises:
        NotFound: If no published model carries the slug. Mapped to HTTP 404.
        ValidationFailure: If the period or the quantity is refused, or the
            period is outside the hire limits of the model. Mapped to HTTP 422.

    """
    return quote_response(quotes.for_model(slug, from_date, to_date, quantity))


def quote_response(answer: ModelQuote) -> QuoteResponse:
    """Write a quote in the shape the contract gives it. Nothing is calculated."""
    quote = answer.quote
    return QuoteResponse(
        from_date=quote.period.start,
        to_date=quote.period.end,
        hire_days=quote.period.days,
        quantity=quote.quantity,
        per_unit=UnitQuoteResponse(
            daily_rate=quote.daily_rate.amount,
            weekly_rate=quote.weekly_rate.amount,
            whole_weeks=quote.period.whole_weeks,
            remainder_days=quote.period.remainder_days,
            basis=BASIS_TO_WIRE[quote.basis],
            amount_ex_vat=quote.unit_amount_ex_vat.amount,
        ),
        subtotal_ex_vat=quote.subtotal_ex_vat.amount,
        discount_percent=quote.discount_percent,
        discount_amount=quote.discount_amount.amount,
        vat_rate=quote.vat_rate_percent,
        vat_amount=quote.vat_amount.amount,
        total_inc_vat=quote.total_inc_vat.amount,
        deposit_per_unit=quote.deposit_per_unit.amount,
        deposit_total=quote.deposit_total.amount,
        late_fee_per_day=answer.late_fee_per_day.amount,
    )
