"""A customer reading and editing their own details (US-05, C-26).

The profile is found by the account that is signed in and by nothing the
caller sends, so there is no key to guess and nobody else's profile to reach.
An account with no customer profile, which is every staff account, is told
there is none.

An edit takes the eight contact and billing fields and no others. The domain
refuses anything else by name, so an account status, a role or a discount
cannot be changed through here whatever the request carried. The name and the
phone number live on the account and on the profile, and both copies are
written together.

An edit that changes something writes one audit event in the same unit of
work (BR-49). The event names the fields that changed and not their values. A
log that can never be rewritten is the wrong place to keep every address a
customer has ever had.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from app.application.audit import audit_event_for
from app.application.identity.account_rules import refused_field
from app.application.use_case import UseCase
from app.domain.customer_account import CustomerDetails
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

PROFILE_ENTITY_TYPE: Final[str] = "customer_profile"
PROFILE_UPDATED_ACTION: Final[str] = "customer.profile_updated"
PROFILE_NOT_FOUND_MESSAGE: Final[str] = "This account has no customer profile."


@dataclass(frozen=True, slots=True)
class ReadProfileQuery:
    """A request by a signed in account for its own profile.

    Attributes:
        actor: The account that is asking.

    """

    actor: Actor


class ReadProfileUseCase(UseCase[ReadProfileQuery, CustomerDetails]):
    """Return the profile of the account that is signed in."""

    def execute(self, command: ReadProfileQuery) -> CustomerDetails:
        """Return the caller's own details.

        Raises:
            NotFound: If the account has no customer profile.

        """
        actor = command.actor
        with self._uow as uow:
            details = uow.customers.details_for_account(actor.user_id)
        logger.info(
            "customer.profile_read",
            extra={"user_id": str(actor.user_id), "found": details is not None},
        )
        if details is None:
            raise NotFound(PROFILE_NOT_FOUND_MESSAGE)
        return details


@dataclass(frozen=True, slots=True)
class UpdateProfileCommand:
    """A request by a customer to change their own contact or billing details.

    Attributes:
        actor: The account that is asking.
        changes: The new value of each field that was sent, by the name the
            domain gives the field. A field that was not sent is not in it.

    """

    actor: Actor
    changes: Mapping[str, str | None]


class UpdateProfileUseCase(UseCase[UpdateProfileCommand, CustomerDetails]):
    """Apply a customer's edits to their own profile, all of them or none."""

    def execute(self, command: UpdateProfileCommand) -> CustomerDetails:
        """Change the fields that were sent and return the profile as it now is.

        Raises:
            NotFound: If the account has no customer profile.
            ValidationFailure: If a field may not be edited or a value is
                refused. The detail names the field as the request named it.

        """
        actor = command.actor
        now = self._clock.now()
        logger.info(
            "customer.profile_update_started",
            extra={"user_id": str(actor.user_id), "field_count": len(command.changes)},
        )
        with self._uow as uow:
            details = uow.customers.details_for_account(actor.user_id, for_update=True)
            if details is None:
                raise NotFound(PROFILE_NOT_FOUND_MESSAGE)
            try:
                changed = details.apply(command.changes)
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            if changed:
                uow.customers.save_details(details)
                uow.audit.record(
                    audit_event_for(
                        actor=actor,
                        entity_type=PROFILE_ENTITY_TYPE,
                        entity_id=details.profile_id,
                        action=PROFILE_UPDATED_ACTION,
                        occurred_at=now,
                        after_state={"changed_fields": list(changed)},
                    )
                )
                uow.commit()
        logger.info(
            "customer.profile_update_finished",
            extra={"user_id": str(actor.user_id), "changed_fields": list(changed)},
        )
        return details
