"""The use case by which an owner sets a customer's trade discount (BR-21).

The discount applies to bookings made from now on. A booking copies the
discount onto its lines when it is created, so changing the profile later
never rewrites an existing booking's price. The use case locks the profile so
two owners changing the same customer take turns, writes the new value and
records `customer.trade_discount_changed` with the old and new percentages in
the same transaction (BR-49). Asking for the value the customer already has
writes nothing and answers as they are.

Only a trade customer can carry a discount. An individual account is refused
with a plain sentence naming the field.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.identity.account_rules import refused_field
from app.application.identity.customer_directory import CustomerSummary
from app.application.identity.customer_lookup import CUSTOMER_NOT_FOUND_MESSAGE, read_customer
from app.application.refusal import refused
from app.application.use_case import UseCase
from app.domain.enums import CustomerType
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor
from app.domain.trade_discount import (
    TRADE_DISCOUNT_FIELD,
    TRADE_ONLY_MESSAGE,
    checked_trade_discount,
)

logger = logging.getLogger(__name__)

CUSTOMER_ENTITY_TYPE: Final[str] = "customer_profile"
TRADE_DISCOUNT_CHANGED_ACTION: Final[str] = "customer.trade_discount_changed"


@dataclass(frozen=True, slots=True)
class ChangeTradeDiscountCommand:
    """A request to set a customer's trade discount.

    Attributes:
        actor: The owner deciding.
        customer_profile_id: The customer.
        percent: The new discount, as a percentage.

    """

    actor: Actor
    customer_profile_id: UUID
    percent: Decimal


class ChangeTradeDiscountUseCase(UseCase[ChangeTradeDiscountCommand, CustomerSummary]):
    """Set the trade discount and record it, in one transaction."""

    def execute(self, command: ChangeTradeDiscountCommand) -> CustomerSummary:
        """Set the discount, or refuse and change nothing.

        Raises:
            NotFound: If there is no customer profile with this key.
            ValidationFailure: If the customer is not a trade account, or the
                value is out of range or carries more than two decimals. The
                detail names `tradeDiscountPercent`.

        """
        profile_id = command.customer_profile_id
        logger.info(
            "customer.trade_discount_change_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "customer_profile_id": str(profile_id),
                "percent": str(command.percent),
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            customer = uow.customers.get_for_update(profile_id)
            if customer is None:
                logger.info("customer.not_found", extra={"customer_profile_id": str(profile_id)})
                raise NotFound(CUSTOMER_NOT_FOUND_MESSAGE, {"customer_profile_id": str(profile_id)})
            if customer.customer_type is not CustomerType.TRADE:
                raise refused(TRADE_DISCOUNT_FIELD, TRADE_ONLY_MESSAGE)
            try:
                after = checked_trade_discount(command.percent)
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            before = customer.trade_discount_percent
            if after == before:
                logger.info(
                    "customer.trade_discount_unchanged",
                    extra={"customer_profile_id": str(profile_id)},
                )
                return read_customer(uow, profile_id)
            uow.customers.save_trade_discount(profile_id, after)
            uow.audit.record(
                audit_event_for(
                    actor=command.actor,
                    entity_type=CUSTOMER_ENTITY_TYPE,
                    entity_id=profile_id,
                    action=TRADE_DISCOUNT_CHANGED_ACTION,
                    occurred_at=now,
                    before_state={TRADE_DISCOUNT_FIELD: str(before)},
                    after_state={TRADE_DISCOUNT_FIELD: str(after)},
                )
            )
            summary = read_customer(uow, profile_id)
            uow.commit()
        logger.info(
            "customer.trade_discount_changed",
            extra={
                "customer_profile_id": str(profile_id),
                "before": str(before),
                "after": str(after),
            },
        )
        return summary
