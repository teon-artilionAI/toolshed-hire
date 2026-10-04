"""The use case by which an administrator sets the standing of a customer (BR-18, US-35).

An administrator moves a customer between ACTIVE, ON_HOLD and BLACKLISTED,
with a reason. In one unit of work the profile is locked, the way a no show
locks it before it counts a strike, so a hold the sweep puts on and a release
an administrator makes at the same moment take turns. The standing is written
and `customer.status_changed` is recorded with the standing before and after
and the reason (BR-49). Nothing else on the profile changes, so releasing a
hold keeps the count of bookings the customer did not collect.

A customer on hold or blacklisted is refused a booking by the rule every
booking already asks, so the change takes effect on the next booking. Asking
for the standing a customer already has writes nothing. The answer is the
`CustomerSummary` the counter reads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.identity.account_rules import refused_field
from app.application.identity.customer_directory import CustomerSummary
from app.application.identity.customer_lookup import CUSTOMER_NOT_FOUND_MESSAGE, read_customer
from app.application.use_case import UseCase
from app.domain.customer_standing import standing_change
from app.domain.enums import AccountStatus
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

CUSTOMER_ENTITY_TYPE: Final[str] = "customer_profile"
CUSTOMER_STATUS_CHANGED_ACTION: Final[str] = "customer.status_changed"
STATUS_KEY: Final[str] = "account_status"
REASON_KEY: Final[str] = "reason"


@dataclass(frozen=True, slots=True)
class ChangeCustomerStandingCommand:
    """A request to set the standing of a customer.

    Attributes:
        actor: The administrator deciding.
        customer_profile_id: The customer.
        account_status: The standing they are to have.
        reason: Why, which the audit event keeps.

    """

    actor: Actor
    customer_profile_id: UUID
    account_status: AccountStatus
    reason: str


class ChangeCustomerStandingUseCase(UseCase[ChangeCustomerStandingCommand, CustomerSummary]):
    """Set the standing of a customer and record it, in one transaction."""

    def execute(self, command: ChangeCustomerStandingCommand) -> CustomerSummary:
        """Set the standing, or refuse and change nothing.

        Raises:
            NotFound: If there is no customer profile with this key.
            ValidationFailure: Naming `reason`, when it is out of bounds.

        """
        profile_id = command.customer_profile_id
        logger.info(
            "customer.status_change_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "customer_profile_id": str(profile_id),
                "account_status": command.account_status.value,
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            customer = uow.customers.get_for_update(profile_id)
            if customer is None:
                logger.info("customer.not_found", extra={"customer_profile_id": str(profile_id)})
                raise NotFound(CUSTOMER_NOT_FOUND_MESSAGE, {"customer_profile_id": str(profile_id)})
            try:
                change = standing_change(
                    customer.account_status, command.account_status, command.reason
                )
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            if not change.changes_anything:
                logger.info(
                    "customer.status_unchanged", extra={"customer_profile_id": str(profile_id)}
                )
                return read_customer(uow, profile_id)
            uow.customers.save_account_status(profile_id, change.after)
            uow.audit.record(
                audit_event_for(
                    actor=command.actor,
                    entity_type=CUSTOMER_ENTITY_TYPE,
                    entity_id=profile_id,
                    action=CUSTOMER_STATUS_CHANGED_ACTION,
                    occurred_at=now,
                    before_state={STATUS_KEY: change.before.value},
                    after_state={STATUS_KEY: change.after.value, REASON_KEY: change.reason},
                )
            )
            summary = read_customer(uow, profile_id)
            uow.commit()
        logger.info(
            "customer.status_changed",
            extra={
                "customer_profile_id": str(profile_id),
                "from_status": change.before.value,
                "to_status": change.after.value,
            },
        )
        return summary
