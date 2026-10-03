"""The identity entities a booking reads, which are the actor, the branch and the customer.

These are plain dataclasses. They hold what a use case needs to know about who
is acting and for whom, and nothing about how either is stored. The SQLModel
classes in the infrastructure layer carry every column. An entity here carries
only the fields a rule or a use case reads, and it gains a field when a rule
first needs it.

The branch scope rule lives here as well (BR-43). Counter staff act for one
branch, so a write aimed at another branch is refused, and every write that
names a branch asks `ensure_branch_scope` before it does anything else. The
sign in account and its lockout rule are in `app.domain.account`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.enums import AccountStatus, UserRole
from app.domain.errors import AccountOnHoldError, BranchScopeError

NO_TRADE_DISCOUNT: Final[Decimal] = Decimal("0.00")
ACCOUNT_STANDING_RULE: Final[str] = "BR-18"
BRANCH_SCOPE_RULE: Final[str] = "BR-43"
BRANCH_SCOPE_MESSAGE: Final[str] = (
    "Counter staff can only work on bookings at their own branch. This one is at another "
    "branch."
)
# An account goes on hold only through the no show rule, so the refusal says so.
ACCOUNT_ON_HOLD_MESSAGE: Final[str] = (
    "This customer account is on hold because three bookings in the last twelve months "
    "were not collected. It cannot make a reservation until an administrator lifts the "
    "hold. Please speak to the branch."
)
ACCOUNT_NOT_IN_GOOD_STANDING_MESSAGE: Final[str] = (
    "This customer account is on hold, so it cannot make a reservation at the moment. "
    "Please speak to the branch."
)


@dataclass(frozen=True, slots=True)
class Actor:
    """The account performing an operation, with the role it held at that moment.

    The role is copied when the request is authenticated and travels with the
    command. The audit event records this copy, so the log still says what the
    actor was allowed to do at the time after a later promotion or demotion.

    Attributes:
        user_id: The account that is acting.
        role: The stored role of that account when the request was served.
        branch_id: The branch the account is scoped to. Counter staff carry
            one. A customer and an administrator carry none.

    """

    user_id: UUID
    role: UserRole
    branch_id: UUID | None = None


def within_branch_scope(actor: Actor, branch_id: UUID) -> bool:
    """Return True when the actor may write at a branch (BR-43).

    Only counter staff are scoped, and only to the branch they are assigned to.
    """
    return actor.role is not UserRole.COUNTER_STAFF or actor.branch_id == branch_id


def ensure_branch_scope(actor: Actor, branch_id: UUID) -> None:
    """Refuse a write by counter staff to a branch that is not their own (BR-43).

    A customer books at whichever branch they choose and an administrator acts
    for all three, so neither is scoped. A counter account that carries no
    branch is refused as well. The database forbids such an account, so
    meeting one means the actor was built wrongly, and the safe answer to
    that is no.

    Args:
        actor: The account that is acting.
        branch_id: The branch the write is aimed at.

    Raises:
        BranchScopeError: If the actor is counter staff and the branch is not
            the one they are assigned to.

    """
    if within_branch_scope(actor, branch_id):
        return
    raise BranchScopeError(
        BRANCH_SCOPE_MESSAGE, {"branch_id": str(branch_id)}, rule=BRANCH_SCOPE_RULE
    )


@dataclass(frozen=True, slots=True)
class Branch:
    """A trading location, as far as a booking needs to know it.

    Attributes:
        id: The branch key.
        code: The short code staff use, for example CBD.
        name: The display name.
        closes_at: When the counter closes, on a clock in Cape Town. A hire
            can no longer start on a day once it has passed (BR-04).

    """

    id: UUID
    code: str
    name: str
    closes_at: time


@dataclass(frozen=True, slots=True)
class CustomerProfile:
    """The hire side of a customer, which is what owns a booking.

    Attributes:
        id: The profile key a reservation points at.
        user_account_id: The sign in account, or None for a walk-in.
        display_name: The name staff see.
        account_status: The standing of the customer (BR-18).
        email: The address of the sign in account, or None for a walk-in. A
            booking confirmation can only be sent when there is one.
        trade_discount_percent: The discount a trade customer is given, which
            the pricing policy takes as an input (BR-21).
        email_verified: True when the holder of the account has proved the
            address. A walk-in has no account, so this is False (BR-47).

    """

    id: UUID
    user_account_id: UUID | None
    display_name: str
    account_status: AccountStatus
    email: str | None
    trade_discount_percent: Decimal = NO_TRADE_DISCOUNT
    email_verified: bool = False

    def ensure_may_book(self) -> None:
        """Refuse a customer whose account is not in good standing (BR-18).

        An account on hold and a blacklisted one are both refused. Only an
        active account may create a reservation or put one on hold. The
        refusal of an account on hold says why it is on hold, which is three
        bookings that were not collected.

        Raises:
            AccountOnHoldError: If the account status is anything but ACTIVE.

        """
        if self.account_status is AccountStatus.ACTIVE:
            return
        message = (
            ACCOUNT_ON_HOLD_MESSAGE
            if self.account_status is AccountStatus.ON_HOLD
            else ACCOUNT_NOT_IN_GOOD_STANDING_MESSAGE
        )
        raise AccountOnHoldError(
            message,
            {"account_status": self.account_status.value},
            rule=ACCOUNT_STANDING_RULE,
        )
