"""What an administrator asks of the staff accounts, as the use cases are handed it (FR-25, US-35).

A new account names every field. An edit names only the fields the request
sent, each as a `Change`, so a field left out keeps its value and a field sent
as null is cleared, which only the phone and the branch allow. The address is
not among the changes, because an account keeps the address it was opened
with, and no command carries a password, because no route reads or sets one.

A branch is named by its code, which is what the office knows it by.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.catalogue.admin_commands import Change
from app.application.identity.staff_read_models import StaffMember
from app.domain.enums import UserRole
from app.domain.identity import Actor


@dataclass(frozen=True, slots=True)
class OpenStaffAccountCommand:
    """A request to open a staff account.

    Attributes:
        actor: The administrator opening it.
        email: The address the person will sign in with.
        full_name: Their name.
        phone: Their number, or None.
        role: COUNTER_STAFF or ADMIN.
        branch_code: The branch of counter staff, and None for an administrator.

    """

    actor: Actor
    email: str
    full_name: str
    phone: str | None
    role: UserRole
    branch_code: str | None


@dataclass(frozen=True, slots=True)
class StaffChanges:
    """The fields of a staff account an edit names, each None when it was left out."""

    full_name: Change[str] | None = None
    phone: Change[str | None] | None = None
    role: Change[UserRole] | None = None
    branch_code: Change[str | None] | None = None


@dataclass(frozen=True, slots=True)
class EditStaffAccountCommand:
    """A request to change some fields of a staff account.

    Attributes:
        actor: The administrator editing it.
        user_id: The account.
        changes: The fields the request named.

    """

    actor: Actor
    user_id: UUID
    changes: StaffChanges


@dataclass(frozen=True, slots=True)
class DeactivateStaffAccountCommand:
    """A request to stop an account signing in, with the reason for it.

    Attributes:
        actor: The administrator deactivating it.
        user_id: The account.
        reason: Why, which the audit event keeps.

    """

    actor: Actor
    user_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class ReactivateStaffAccountCommand:
    """A request to let a deactivated account sign in again.

    Attributes:
        actor: The administrator reactivating it.
        user_id: The account.

    """

    actor: Actor
    user_id: UUID


@dataclass(frozen=True, slots=True)
class StaffAccountOpened:
    """A new staff account, and whether the link to choose a password could be sent.

    Attributes:
        member: The account as the administrator reads it.
        email_deliverable: True when the email gateway took the message with
            the link. False when it could not be handed over, in which case
            the person asks for a new link from the sign in page once mail
            reaches them.

    """

    member: StaffMember
    email_deliverable: bool
