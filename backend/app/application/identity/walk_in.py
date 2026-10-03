"""The use case that registers a walk-in at the counter (US-20).

A customer with no online account is registered by a counter assistant. They
get a customer profile and no sign in account, so no password is set and no
message is sent. A booking made for them at the counter names this profile.

The profile is registered at a branch. A counter assistant registers it at
their own branch, and naming another one is a write at another branch, which
is refused (BR-43). An administrator belongs to no branch, so one has to name
the branch.

The profile and its audit event are written in one unit of work (BR-49). The
event says what kind of customer was registered and where, and names none of
their details, because a log that can never be rewritten is the wrong place to
keep a customer's phone number.

A refusal names its field the way the request did, so a form can put the
sentence beside the right input.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from app.application.audit import audit_event_for
from app.application.identity.account_rules import refused_field
from app.application.identity.customer_directory import CustomerSummary
from app.application.identity.customer_lookup import read_customer
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.enums import CustomerType, IdDocType
from app.domain.errors import ValidationFailure
from app.domain.identity import Actor, Branch, ensure_branch_scope
from app.domain.walk_in import WalkInCustomer

logger = logging.getLogger(__name__)

CUSTOMER_ENTITY_TYPE: Final[str] = "customer_profile"
WALK_IN_REGISTERED_ACTION: Final[str] = "customer.walk_in_registered"
BRANCH_PARAMETER: Final[str] = "branchCode"
BRANCH_REQUIRED_MESSAGE: Final[str] = "Choose the branch the customer is registered at."
UNKNOWN_BRANCH_MESSAGE: Final[str] = "Choose one of our branches."


@dataclass(frozen=True, slots=True)
class RegisterWalkInCommand:
    """A request to register a customer who has no login.

    Attributes:
        actor: The member of staff at the counter.
        display_name: The name staff will see.
        phone: The number the branch can reach the customer on.
        id_document_type: The kind of identity document presented.
        id_document_last4: Its last four characters.
        billing_address_line1: The first line of the billing address.
        billing_suburb: The suburb.
        billing_city: The city.
        billing_postal_code: The postal code.
        customer_type: Whether they hire as an individual or as a trade.
        company_name: The company of a trade customer.
        vat_number: Its VAT number.
        branch_code: The branch to register them at. An administrator names
            one. Counter staff may leave it out.

    """

    actor: Actor
    display_name: str
    phone: str
    id_document_type: IdDocType
    id_document_last4: str
    billing_address_line1: str
    billing_suburb: str
    billing_city: str
    billing_postal_code: str
    customer_type: CustomerType = CustomerType.INDIVIDUAL
    company_name: str | None = None
    vat_number: str | None = None
    branch_code: str | None = None


class RegisterWalkInUseCase(UseCase[RegisterWalkInCommand, CustomerSummary]):
    """Register a customer profile with no account, in one transaction."""

    def execute(self, command: RegisterWalkInCommand) -> CustomerSummary:
        """Register the walk-in and return them as the counter sees a customer.

        Raises:
            ValidationFailure: If a field is refused, or an administrator names
                no branch or one that does not trade. The detail names the field.
            BranchScopeError: If counter staff name another branch.

        """
        actor = command.actor
        logger.info(
            "customer.walk_in_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "customer_type": command.customer_type.value,
                "branch_named": command.branch_code is not None,
            },
        )
        customer = _checked(command)
        now = self._clock.now()
        with self._uow as uow:
            branch = _registering_branch(uow, actor, command.branch_code)
            profile_id = uow.customers.add_walk_in(
                registered_branch_id=branch.id, customer=customer
            )
            uow.audit.record(
                audit_event_for(
                    actor=actor,
                    entity_type=CUSTOMER_ENTITY_TYPE,
                    entity_id=profile_id,
                    action=WALK_IN_REGISTERED_ACTION,
                    occurred_at=now,
                    after_state={
                        "customer_type": customer.customer_type.value,
                        "home_branch_code": branch.code,
                        "has_login": False,
                    },
                )
            )
            summary = read_customer(uow, profile_id)
            uow.commit()
        logger.info(
            "customer.walk_in_registered",
            extra={"customer_profile_id": str(profile_id), "home_branch_code": branch.code},
        )
        return summary


def _checked(command: RegisterWalkInCommand) -> WalkInCustomer:
    """Return the walk-in's details, or refuse the field that is wrong, named as sent."""
    try:
        return WalkInCustomer.registering(
            display_name=command.display_name,
            phone=command.phone,
            id_document_type=command.id_document_type,
            id_document_last4=command.id_document_last4,
            billing_address_line1=command.billing_address_line1,
            billing_suburb=command.billing_suburb,
            billing_city=command.billing_city,
            billing_postal_code=command.billing_postal_code,
            customer_type=command.customer_type,
            company_name=command.company_name,
            vat_number=command.vat_number,
        )
    except ValidationFailure as failure:
        raise refused_field(failure) from failure


def _registering_branch(uow: UnitOfWork, actor: Actor, branch_code: str | None) -> Branch:
    """Return the branch the walk-in is registered at.

    Raises:
        ValidationFailure: Naming `branchCode` when an administrator names no
            branch, or the code names no trading branch.
        BranchScopeError: If counter staff name a branch that is not theirs.

    """
    if branch_code is None and actor.branch_id is not None:
        own = uow.branches.get(actor.branch_id)
        if own is not None:
            return own
    if branch_code is None:
        raise refused(BRANCH_PARAMETER, BRANCH_REQUIRED_MESSAGE)
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        raise refused(BRANCH_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    ensure_branch_scope(actor, branch.id)
    return branch
