"""Anonymising one customer, which the owner does when a customer asks (#113).

The owner gives a reason, which the audit event keeps. In one unit of work the
profile and the account are locked, the customer is refused if they were
anonymised already or still have a booking open, a hire not settled or money
owing, and otherwise every identifying column the personal data map names on
the profile and the account is written over with the values of
`app.domain.anonymisation`. The account is made inactive, so nobody can sign in
to it, and its refresh sessions are revoked and lose their browser and address.
What someone may have typed about the customer into their bookings, hire
items, damage reports and waived charges is cleared or replaced, and their
notifications name an address that never delivers.

Hires, charges and deposits stay, linked to the anonymised profile, because
they are financial records kept for five years. `audit_event` is never touched.
The application role may only add to it (BR-49), and the trail is the legal
record of what was done, this anonymisation included. `customer.anonymised` is
recorded with the trigger and, for a request, the reason, and never with a
value the customer had.

`anonymise_in` is the work itself, inside a unit of work the caller opened, so
the monthly job anonymises a batch in one transaction with exactly the same
steps.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.identity.account_rules import refused_field
from app.application.identity.anonymisation_ports import ErasedRows
from app.application.identity.customer_directory import CustomerSummary
from app.application.identity.customer_lookup import CUSTOMER_NOT_FOUND_MESSAGE, read_customer
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.anonymisation import (
    AnonymisationTrigger,
    anonymised_account,
    anonymised_profile,
    ensure_may_be_anonymised,
    ensure_still_dormant,
)
from app.domain.audit import StateValue
from app.domain.enums import RevokeReason
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor
from app.domain.override_reason import written_reason

logger = logging.getLogger(__name__)

CUSTOMER_ENTITY_TYPE: Final[str] = "customer_profile"
CUSTOMER_ANONYMISED_ACTION: Final[str] = "customer.anonymised"
TRIGGER_KEY: Final[str] = "trigger"
REASON_KEY: Final[str] = "reason"
SESSIONS_REVOKED_KEY: Final[str] = "sessions_revoked"


@dataclass(frozen=True, slots=True)
class Anonymised:
    """What one anonymisation did, for the log and the job's counts.

    Attributes:
        customer_profile_id: The customer.
        erased: How many rows of each kind were written over.
        sessions_revoked: How many live refresh sessions were ended.

    """

    customer_profile_id: UUID
    erased: ErasedRows
    sessions_revoked: int


@dataclass(frozen=True, slots=True)
class AnonymiseCustomerCommand:
    """The owner's request to anonymise a customer.

    Attributes:
        actor: The administrator deciding.
        customer_profile_id: The customer.
        reason: Why, which the audit event keeps.

    """

    actor: Actor
    customer_profile_id: UUID
    reason: str


def anonymise_in(
    uow: UnitOfWork,
    *,
    customer_profile_id: UUID,
    trigger: AnonymisationTrigger,
    actor: Actor | None,
    reason: str | None,
    now: datetime,
    dormant_since: datetime | None = None,
) -> Anonymised:
    """Anonymise one customer inside a unit of work the caller opened and commits.

    Nothing is written before every refusal has been asked, so a refused
    customer leaves the transaction as it found it.

    Args:
        uow: The open unit of work.
        customer_profile_id: The customer.
        trigger: Whether the owner asked or the monthly job found them.
        actor: The administrator, or None for the job.
        reason: The owner's reason, or None for the job.
        now: The instant, which the profile and the audit event keep.
        dormant_since: For the job, the cutoff the account must not have
            signed in since. None for a request, which asks no such thing.

    Raises:
        NotFound: If there is no customer with this key.
        StateTransitionError: If the customer was anonymised already, still
            has something open, or signed in since `dormant_since`.

    """
    eraser = uow.personal_data
    subject = eraser.subject_for_update(customer_profile_id)
    if subject is None:
        logger.info(
            "customer.not_found", extra={"customer_profile_id": str(customer_profile_id)}
        )
        raise NotFound(
            CUSTOMER_NOT_FOUND_MESSAGE, {"customer_profile_id": str(customer_profile_id)}
        )
    if dormant_since is not None:
        ensure_still_dormant(subject.last_signed_in_at, dormant_since)
    ensure_may_be_anonymised(subject.anonymised_at, eraser.open_matters(customer_profile_id))
    account = (
        anonymised_account(customer_profile_id) if subject.user_account_id is not None else None
    )
    revoked = 0
    if subject.user_account_id is not None:
        revoked = uow.sessions.revoke_all_for_account(
            user_account_id=subject.user_account_id, reason=RevokeReason.ADMIN_REVOKE, at=now
        )
    erased = eraser.erase(
        subject, profile=anonymised_profile(subject.customer_type), account=account, at=now
    )
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=CUSTOMER_ENTITY_TYPE,
            entity_id=customer_profile_id,
            action=CUSTOMER_ANONYMISED_ACTION,
            occurred_at=now,
            after_state=_after_state(trigger, reason, erased, revoked),
        )
    )
    return Anonymised(
        customer_profile_id=customer_profile_id, erased=erased, sessions_revoked=revoked
    )


def _after_state(
    trigger: AnonymisationTrigger, reason: str | None, erased: ErasedRows, revoked: int
) -> dict[str, StateValue]:
    """Return what the audit event keeps, which is never a value the customer had."""
    state: dict[str, StateValue] = {TRIGGER_KEY: trigger.value}
    if reason is not None:
        state[REASON_KEY] = reason
    state.update(asdict(erased))
    state[SESSIONS_REVOKED_KEY] = revoked
    return state


class AnonymiseCustomerUseCase(UseCase[AnonymiseCustomerCommand, CustomerSummary]):
    """Anonymise a customer the owner names, and record it, in one transaction."""

    def execute(self, command: AnonymiseCustomerCommand) -> CustomerSummary:
        """Anonymise the customer, or refuse and change nothing.

        Returns:
            The customer as the counter now reads them.

        Raises:
            ValidationFailure: Naming `reason`, when it is out of bounds.
            NotFound: If there is no customer with this key.
            StateTransitionError: If the customer was anonymised already or
                still has something open.

        """
        profile_id = command.customer_profile_id
        logger.info(
            "customer.anonymisation_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "customer_profile_id": str(profile_id),
                "trigger": AnonymisationTrigger.REQUEST.value,
            },
        )
        try:
            reason = written_reason(command.reason)
        except ValidationFailure as failure:
            raise refused_field(failure) from failure
        now = self._clock.now()
        with self._uow as uow:
            done = anonymise_in(
                uow,
                customer_profile_id=profile_id,
                trigger=AnonymisationTrigger.REQUEST,
                actor=command.actor,
                reason=reason,
                now=now,
            )
            summary = read_customer(uow, profile_id)
            uow.commit()
        logger.info(
            "customer.anonymised",
            extra={
                "customer_profile_id": str(profile_id),
                "trigger": AnonymisationTrigger.REQUEST.value,
                "sessions_revoked": done.sessions_revoked,
                **asdict(done.erased),
            },
        )
        return summary
