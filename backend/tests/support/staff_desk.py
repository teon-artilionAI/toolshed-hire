"""The staff account use cases wired over one in memory store, for the unit tests.

A desk holds a store with the three branches, an administrator who acts and a
second one, and builds each use case over a unit of work of its own, the way a
request would. Opening an account hashes with the counting hasher and sends
through the fake gateway, so a test can read the link that was sent and see
that a hash was made and never a password chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from app.application.identity.account_mail import AccountMailer
from app.application.identity.staff_access import (
    DeactivateStaffAccountUseCase,
    ReactivateStaffAccountUseCase,
)
from app.application.identity.staff_accounts import OpenStaffAccountUseCase
from app.application.identity.staff_commands import (
    DeactivateStaffAccountCommand,
    EditStaffAccountCommand,
    OpenStaffAccountCommand,
    ReactivateStaffAccountCommand,
    StaffAccountOpened,
    StaffChanges,
)
from app.application.identity.staff_edit import EditStaffAccountUseCase
from app.application.identity.staff_read_models import StaffMember
from app.domain.account import Account
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.infrastructure.notification import FakeEmailGateway
from tests.support.clock import FixedClock
from tests.support.memory_crypto import CountingPasswordHasher
from tests.support.memory_register import a_branch
from tests.support.memory_staff import (
    MemoryStaffDirectory,
    MemoryStaffUnitOfWork,
    StaffStore,
)

ORIGIN: Final[str] = "https://toolshed-hire.example.test"
NEW_EMAIL: Final[str] = "thandi.mokoena@toolshedhire.co.za"
REASON: Final[str] = "Left the business at the end of September."


def actor_of(account: Account) -> Actor:
    """Return an account as the actor of an operation."""
    return Actor(user_id=account.id, role=account.role, branch_id=account.branch_id)


@dataclass
class StaffDesk:
    """A store, two administrators, and the use cases over the store."""

    store: StaffStore
    owner: Account
    bookkeeper: Account
    gateway: FakeEmailGateway = field(default_factory=FakeEmailGateway)
    hasher: CountingPasswordHasher = field(default_factory=CountingPasswordHasher)
    clock: FixedClock = field(default_factory=FixedClock)

    def open(self, actor: Account | None = None, **changes: object) -> StaffAccountOpened:
        """Open a counter assistant's account at CBD, with any field changed."""
        values: dict[str, object] = {
            "actor": actor_of(actor or self.owner),
            "email": NEW_EMAIL,
            "full_name": "Thandi Mokoena",
            "phone": "082 441 7719",
            "role": UserRole.COUNTER_STAFF,
            "branch_code": "CBD",
            **changes,
        }
        use_case = OpenStaffAccountUseCase(
            MemoryStaffUnitOfWork(self.store),
            self.clock,
            MemoryStaffDirectory(self.store),
            self.hasher,
            AccountMailer(self.gateway, ORIGIN),
        )
        return use_case.execute(OpenStaffAccountCommand(**values))

    def edit(
        self, account: Account, changes: StaffChanges, actor: Account | None = None
    ) -> StaffMember:
        """Edit an account as an administrator."""
        use_case = EditStaffAccountUseCase(
            MemoryStaffUnitOfWork(self.store), self.clock, MemoryStaffDirectory(self.store)
        )
        return use_case.execute(
            EditStaffAccountCommand(
                actor=actor_of(actor or self.owner), user_id=account.id, changes=changes
            )
        )

    def deactivate(
        self, account: Account, actor: Account | None = None, reason: str = REASON
    ) -> StaffMember:
        """Deactivate an account as an administrator."""
        use_case = DeactivateStaffAccountUseCase(
            MemoryStaffUnitOfWork(self.store), self.clock, MemoryStaffDirectory(self.store)
        )
        return use_case.execute(
            DeactivateStaffAccountCommand(
                actor=actor_of(actor or self.owner), user_id=account.id, reason=reason
            )
        )

    def reactivate(self, account: Account, actor: Account | None = None) -> StaffMember:
        """Reactivate an account as an administrator."""
        use_case = ReactivateStaffAccountUseCase(
            MemoryStaffUnitOfWork(self.store), self.clock, MemoryStaffDirectory(self.store)
        )
        return use_case.execute(
            ReactivateStaffAccountCommand(actor=actor_of(actor or self.owner), user_id=account.id)
        )


def staff_desk() -> StaffDesk:
    """Return a desk with three branches and two active administrators."""
    store = StaffStore(
        branches={code: a_branch(code, name) for code, name in _BRANCHES},
    )
    owner = store.keep(role=UserRole.ADMIN, full_name="Pieter Kleynhans")
    bookkeeper = store.keep(role=UserRole.ADMIN, full_name="Anne Kleynhans")
    return StaffDesk(store=store, owner=owner, bookkeeper=bookkeeper)


_BRANCHES: Final[tuple[tuple[str, str], ...]] = (
    ("CBD", "Cape Town CBD"),
    ("BLV", "Bellville"),
    ("SMW", "Somerset West"),
)

__all__ = ["NEW_EMAIL", "ORIGIN", "REASON", "StaffDesk", "actor_of", "staff_desk"]
