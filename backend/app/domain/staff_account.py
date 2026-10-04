"""The staff accounts an administrator keeps, and the rules of a role and a branch (FR-25, US-35).

A staff account is a sign in account whose role is COUNTER_STAFF or ADMIN. A
customer's account is never one, because a customer is kept through their
profile. Counter staff work at one branch and an administrator at none, which
the database also holds with `ck_user_account_branch_scope`. A rule broken
here is refused with a sentence naming the field, before the constraint is
ever reached.

Two rules keep somebody able to run the business. The last active
administrator can never be deactivated or given another role, and an
administrator cannot deactivate their own account. Both are refused as an
illegal move, which is a 409, because the request is well formed and loses to
the state the accounts are in. The use cases ask them with every active
administrator locked, so two administrators demoting each other at the same
moment take turns, and the second is asked again once the first has
committed.

A new account is given a password hash of a random value that is thrown away,
so nobody knows a password that opens it, and a reset token, so the person
chooses their own password through the reset flow every account already has.
Nothing here reads or sets a password.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final
from uuid import UUID, uuid4

from app.domain.account import Account
from app.domain.account_tokens import PendingToken
from app.domain.customer_account import FULL_NAME, PHONE, REFUSED_FIELD, cleaned_value
from app.domain.enums import UserRole
from app.domain.errors import StateTransitionError, ValidationFailure

STAFF_ROLES: Final[frozenset[UserRole]] = frozenset({UserRole.COUNTER_STAFF, UserRole.ADMIN})

# The fields of a staff account, named the way the domain names them.
EMAIL: Final[str] = "email"
ROLE: Final[str] = "role"
BRANCH_CODE: Final[str] = "branch_code"
STAFF_FULL_NAME: Final[str] = FULL_NAME
STAFF_PHONE: Final[str] = PHONE

# The states the two refusals of a move name, beside the roles themselves.
ACTIVE_STATE: Final[str] = "ACTIVE"
INACTIVE_STATE: Final[str] = "INACTIVE"

STAFF_RULE: Final[str] = "US-35"
BRANCH_SCOPE_RULE: Final[str] = "BR-43"

NOT_A_STAFF_ROLE_MESSAGE: Final[str] = (
    "Choose Counter Staff or Admin. Customers are kept through their profile."
)
BRANCH_NEEDED_MESSAGE: Final[str] = "Counter staff work at one branch. Choose it."
NO_BRANCH_FOR_ADMIN_MESSAGE: Final[str] = (
    "An administrator works for every branch, so leave the branch empty."
)
LAST_ADMINISTRATOR_MESSAGE: Final[str] = (
    "This is the last active administrator. Make somebody else an administrator first."
)
OWN_ACCOUNT_MESSAGE: Final[str] = (
    "You cannot deactivate your own account. Ask another administrator to do it."
)


@dataclass(frozen=True, slots=True)
class StaffDetails:
    """What an administrator decides about a staff account, apart from its address and branch.

    The branch travels beside these, as a key, because a request names it by
    its code and the key is only known once the code has been looked up.

    Attributes:
        full_name: The name of the person.
        phone: The number they can be reached on, or None.
        role: COUNTER_STAFF or ADMIN.

    """

    full_name: str
    phone: str | None
    role: UserRole


def _refusal(field: str, message: str, *, rule: str | None = None) -> ValidationFailure:
    """Return the failure for one refused field."""
    return ValidationFailure(message, {REFUSED_FIELD: field}, rule=rule)


def ensure_staff_role(role: UserRole) -> None:
    """Refuse a role that is not a staff role.

    Raises:
        ValidationFailure: If the role is CUSTOMER. The detail names `role`.

    """
    if role not in STAFF_ROLES:
        raise _refusal(ROLE, NOT_A_STAFF_ROLE_MESSAGE, rule=STAFF_RULE)


def ensure_branch_fits_role(role: UserRole, *, has_branch: bool) -> None:
    """Refuse counter staff with no branch and an administrator with one (BR-43).

    Raises:
        ValidationFailure: Naming `branch_code`.

    """
    if role is UserRole.COUNTER_STAFF and not has_branch:
        raise _refusal(BRANCH_CODE, BRANCH_NEEDED_MESSAGE, rule=BRANCH_SCOPE_RULE)
    if role is UserRole.ADMIN and has_branch:
        raise _refusal(BRANCH_CODE, NO_BRANCH_FOR_ADMIN_MESSAGE, rule=BRANCH_SCOPE_RULE)


def checked_staff_details(details: StaffDetails, *, has_branch: bool) -> StaffDetails:
    """Return the details trimmed, or refuse the first field that breaks a rule.

    The name is required and at most 120 characters. The phone may be left
    empty, which keeps none, and is otherwise held to the rule a customer's
    number is held to. The role has to be a staff role, and the branch has to
    fit it.

    Args:
        details: The name, the phone and the role.
        has_branch: True when the account will belong to a branch.

    Raises:
        ValidationFailure: Naming the field.

    """
    full_name = cleaned_value(STAFF_FULL_NAME, details.full_name)
    phone = details.phone
    kept_phone = None if phone is None or not phone.strip() else cleaned_value(STAFF_PHONE, phone)
    ensure_staff_role(details.role)
    ensure_branch_fits_role(details.role, has_branch=has_branch)
    return StaffDetails(full_name=str(full_name), phone=kept_phone, role=details.role)


def branch_kept_for(role: UserRole, branch_id: UUID | None, *, branch_named: bool) -> UUID | None:
    """Return the branch an account keeps once an edit has set its role.

    An administrator belongs to no branch, so an edit that makes somebody an
    administrator and names no branch lets go of the branch they had. A
    branch the edit does name is kept, so naming one for an administrator is
    still refused.

    Args:
        role: The role the account will hold.
        branch_id: The branch it will hold, as the edit left it.
        branch_named: True when the edit named a branch.

    """
    if role is UserRole.ADMIN and not branch_named:
        return None
    return branch_id


def details_of(account: Account) -> StaffDetails:
    """Return the name, the phone and the role of an account, as it stands."""
    return StaffDetails(full_name=account.full_name, phone=account.phone, role=account.role)


def with_details(account: Account, details: StaffDetails, branch_id: UUID | None) -> Account:
    """Return the account holding the details and the branch, and everything else as it was."""
    return replace(
        account,
        full_name=details.full_name,
        phone=details.phone,
        role=details.role,
        branch_id=branch_id,
    )


def deactivated(account: Account) -> Account:
    """Return the account deactivated, with any reset link it was sent withdrawn.

    The rows and the history of the account are kept (BR-51). A reset link
    still pending would let the person choose a password while they cannot
    sign in, and a reactivation would then bring that password back, so it
    stops working here.
    """
    return replace(account, is_active=False, password_reset=None)


def reactivated(account: Account) -> Account:
    """Return the account active again, with the password it already had."""
    return replace(account, is_active=True)


def new_staff_account(
    *,
    email: str,
    unusable_password_hash: str,
    details: StaffDetails,
    branch_id: UUID | None,
    reset: PendingToken,
) -> Account:
    """Return a new staff account, with no password anyone knows and a reset pending.

    Args:
        email: The address the person will sign in with, in lower case.
        unusable_password_hash: The hash of a random value nobody kept.
        details: The checked name, phone and role.
        branch_id: The branch of counter staff, and None for an administrator.
        reset: The reset token the person chooses their password with.

    """
    account = Account(
        id=uuid4(),
        email=email,
        password_hash=unusable_password_hash,
        role=details.role,
        full_name=details.full_name,
        phone=details.phone,
        branch_id=branch_id,
    )
    account.start_password_reset(reset)
    return account


def counts_as_administrator(account: Account) -> bool:
    """Return True for an active administrator, who keeps the business running."""
    return account.role is UserRole.ADMIN and account.is_active


def ensure_an_administrator_remains(
    account: Account, *, after: Account, active_administrators: frozenset[UUID]
) -> None:
    """Refuse a change that would leave no active administrator.

    Args:
        account: The account as it stands.
        after: The same account as the change would leave it.
        active_administrators: Every active administrator, locked by the
            caller for the rest of the transaction.

    Raises:
        StateTransitionError: If the account is the last active administrator
            and the change deactivates it or gives it another role.

    """
    if not counts_as_administrator(account) or counts_as_administrator(after):
        return
    if active_administrators - {account.id}:
        return
    if after.is_active:
        from_status, to_status = account.role.value, after.role.value
    else:
        from_status, to_status = ACTIVE_STATE, INACTIVE_STATE
    raise StateTransitionError(
        LAST_ADMINISTRATOR_MESSAGE, from_status=from_status, to_status=to_status, rule=STAFF_RULE
    )


def ensure_not_own_account(actor_id: UUID, account_id: UUID) -> None:
    """Refuse an administrator who asks to deactivate their own account.

    Raises:
        StateTransitionError: If the two keys are the same.

    """
    if actor_id == account_id:
        raise StateTransitionError(
            OWN_ACCOUNT_MESSAGE,
            from_status=ACTIVE_STATE,
            to_status=INACTIVE_STATE,
            rule=STAFF_RULE,
        )
