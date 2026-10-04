"""The port the administrator writes staff accounts through (FR-25, US-35).

An account is read, locked and added through the account repository every
sign in already uses. What staff management adds is two things that
repository does not do. It locks every active administrator at once, which is
what the rule about the last administrator stands on, and it writes the name,
the phone, the role, the branch and whether the account may sign in.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.account import Account


class StaffRepository(Protocol):
    """Where the administrator's changes to a staff account are written."""

    def lock_active_administrators(self) -> frozenset[UUID]:
        """Return the key of every active administrator, each locked until the transaction ends.

        The rows are locked in the order of their keys, so every transaction
        that asks takes them in the same order and two can never wait on each
        other. A second caller waits for the first to commit and is then
        answered from what it committed.
        """
        ...

    def save_staff(self, account: Account) -> None:
        """Write the name, the phone, the role, the branch and whether the account is active."""
        ...


__all__ = ["StaffRepository"]
