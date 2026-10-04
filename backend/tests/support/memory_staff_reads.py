"""The staff accounts of the in memory staff store, as the administrator reads them.

`MemoryStaffDirectory` answers the `StaffDirectory` port from what is
committed, by name, and forgets everything when the store says so, which a
real commit never does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.application.identity.staff_read_models import StaffMember, StaffPage, StaffSearch
from app.domain.account import Account
from app.domain.enums import UserRole
from tests.support.clock import DEFAULT_INSTANT

if TYPE_CHECKING:
    from tests.support.memory_staff import StaffStore


class MemoryStaffDirectory:
    """The staff accounts as the administrator reads them, from what is committed."""

    def __init__(self, store: StaffStore) -> None:
        """Bind to the store whose committed accounts are read."""
        self._store = store

    def page(self, search: StaffSearch) -> StaffPage:
        """Return one page of the committed staff accounts that match, by name."""
        found = [
            member
            for member in (self._member(account) for account in self._staff())
            if (search.role is None or member.role is search.role)
            and (search.active is None or member.is_active is search.active)
            and (search.text is None or search.text.lower() in member.full_name.lower())
        ]
        found.sort(key=lambda member: (member.full_name, str(member.id)))
        chosen = found[search.offset : search.offset + search.page_size]
        return StaffPage(
            items=tuple(chosen), page=search.page, page_size=search.page_size, total=len(found)
        )

    def one(self, user_id: UUID) -> StaffMember | None:
        """Return one committed staff account, unless the test made the read forget it."""
        if self._store.forget_answers:
            return None
        account = next((a for a in self._staff() if a.id == user_id), None)
        return self._member(account) if account is not None else None

    def _staff(self) -> list[Account]:
        """Return every committed account that is not a customer's."""
        return [
            account
            for account in self._store.committed.accounts.values()
            if account.role is not UserRole.CUSTOMER
        ]

    def _member(self, account: Account) -> StaffMember:
        """Return one account as the administrator reads it."""
        branch = next(
            (b for b in self._store.branches.values() if b.id == account.branch_id), None
        )
        return StaffMember(
            id=account.id,
            email=account.email,
            full_name=account.full_name,
            phone=account.phone,
            role=account.role,
            branch_code=branch.code if branch is not None else None,
            is_active=account.is_active,
            email_verified=account.email_verified,
            last_login_at=account.last_login_at,
            locked_until=account.locked_until,
            created_at=DEFAULT_INSTANT,
        )


__all__ = ["MemoryStaffDirectory"]
