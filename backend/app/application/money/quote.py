"""Quoting a hire, which is FR-05.

A customer sees what a hire will cost before reserving it. Nothing is held and
nothing is written, so there is no unit of work here.

This module works out no price. It checks that the question may be asked,
reads the published model, copies its rates into a `LineSnapshot` and hands
that to the pricing policy it was built with. Every figure in the answer comes
from the policy (BR-21). The late fee is the one amount that is passed through
as the catalogue holds it, because nothing is calculated from it here.

The question is held to the limits of a booking, through the same checks the
availability search uses, so a quote is never given for a hire that could not
then be booked.

The trade discount is an input. A caller that knows the customer passes the
discount on their profile, and a caller that does not passes none.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.application.availability.hire_request import (
    ensure_quantity_in_range,
    ensure_within_hire_limits,
    requested_period,
)
from app.application.catalogue.browse import MODEL_NOT_FOUND_MESSAGE
from app.application.catalogue.ports import CatalogueQuery
from app.application.catalogue.read_models import ModelDetail
from app.application.clock import Clock
from app.domain.errors import NotFound
from app.domain.money import Money
from app.domain.policies.pricing import (
    NO_DISCOUNT_PERCENT,
    HireQuote,
    LineSnapshot,
    PricingPolicy,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelQuote:
    """What hiring one published model for a period will cost.

    Attributes:
        slug: The slug of the model that was priced.
        quote: The amounts, as the pricing policy worked them out.
        late_fee_per_day: The fee for each day a unit comes back late, as the
            catalogue holds it. It is shown beside the quote and is not part
            of any total in it.

    """

    slug: str
    quote: HireQuote
    late_fee_per_day: Money


def snapshot_of(model: ModelDetail, quantity: int) -> LineSnapshot:
    """Copy the figures a price is worked out from off a catalogue entry.

    The policy is handed this copy and never the entry, so a quote is worked
    out from the rates as they stood when the copy was taken (BR-20).
    """
    return LineSnapshot(
        daily_rate=Money.create(model.daily_rate),
        weekly_rate=Money.create(model.weekly_rate),
        deposit=Money.create(model.deposit_amount),
        quantity=quantity,
    )


class QuoteHire:
    """What a hire will cost, as a visitor asks it."""

    def __init__(self, catalogue: CatalogueQuery, pricing: PricingPolicy, clock: Clock) -> None:
        """Keep the port the model is read through, the policy and the clock.

        Args:
            catalogue: Finds the published model.
            pricing: The policy that works out the price.
            clock: Where the current business day comes from.

        """
        self._catalogue = catalogue
        self._pricing = pricing
        self._clock = clock

    def for_model(
        self,
        slug: str,
        start: date,
        end: date,
        quantity: int,
        discount_percent: Decimal = NO_DISCOUNT_PERCENT,
    ) -> ModelQuote:
        """Price a hire of one published model.

        Args:
            slug: The slug of a published model.
            start: The first day of the hire.
            end: The day the equipment comes back, which is not charged.
            quantity: How many units are wanted.
            discount_percent: The trade discount of the customer, when the
                caller knows who is asking. None is applied when it is omitted.

        Raises:
            ValidationFailure: If the period or the quantity is refused, or if
                the period is outside the hire limits of the model. The
                failure names the parameter.
            NotFound: If no published model carries the slug.

        """
        period = requested_period(start, end, self._clock.today())
        ensure_quantity_in_range(quantity)
        logger.info(
            "quote.requested",
            extra={
                "slug": slug,
                "period": period.as_postgres_daterange(),
                "quantity": quantity,
                "discount_percent": str(discount_percent),
            },
        )
        model = self._catalogue.find_model(slug)
        if model is None:
            logger.info(
                "quote.model_not_found",
                extra={"slug": slug, "attempted": "quote a hire of a catalogue model"},
            )
            raise NotFound(MODEL_NOT_FOUND_MESSAGE, {"slug": slug})
        ensure_within_hire_limits(model, period)

        quote = self._pricing.quote(snapshot_of(model, quantity), period, discount_percent)
        logger.info(
            "quote.priced",
            extra={
                "slug": slug,
                "sku": model.sku,
                "period": period.as_postgres_daterange(),
                "hire_days": period.days,
                "quantity": quantity,
                "pricing_policy": self._pricing.name(),
                "basis": quote.basis.value,
                "discount_percent": str(quote.discount_percent),
                "amount_ex_vat": str(quote.amount_ex_vat.amount),
                "vat_amount": str(quote.vat_amount.amount),
                "total_inc_vat": str(quote.total_inc_vat.amount),
            },
        )
        return ModelQuote(
            slug=slug,
            quote=quote,
            late_fee_per_day=Money.create(model.late_fee_per_day).rounded(),
        )
