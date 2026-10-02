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
from uuid import UUID

from app.domain.enums import AccountStatus, UserRole
from app.domain.errors import BranchScopeError


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
    if actor.role is not UserRole.COUNTER_STAFF or actor.branch_id == branch_id:
        return
    raise BranchScopeError(
        f"Counter account {actor.user_id} attempted to write to branch {branch_id}, and is "
        f"assigned to branch {actor.branch_id}. Counter staff act for their own branch only.",
        {"branch_id": str(branch_id)},
    )


@dataclass(frozen=True, slots=True)
class Branch:
    """A trading location, as far as a booking needs to know it.

    Attributes:
        id: The branch key.
        code: The short code staff use, for example CBD.
        name: The display name.

    """

    id: UUID
    code: str
    name: str


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

    """

    id: UUID
    user_account_id: UUID | None
    display_name: str
    account_status: AccountStatus
    email: str | None
