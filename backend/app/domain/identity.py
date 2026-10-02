"""The identity entities a booking reads, which are the actor, the branch and the customer.

These are plain dataclasses. They hold what a use case needs to know about who
is acting and for whom, and nothing about how either is stored. The SQLModel
classes in the infrastructure layer carry every column. An entity here carries
only the fields a rule or a use case reads, and it gains a field when a rule
first needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.enums import AccountStatus, UserRole


@dataclass(frozen=True, slots=True)
class Actor:
    """The account performing an operation, with the role it held at that moment.

    The role is copied when the request is authenticated and travels with the
    command. The audit event records this copy, so the log still says what the
    actor was allowed to do at the time after a later promotion or demotion.

    Attributes:
        user_id: The account that is acting.
        role: The stored role of that account when the request was served.

    """

    user_id: UUID
    role: UserRole


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
