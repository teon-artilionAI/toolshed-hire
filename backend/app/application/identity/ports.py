"""The identity ports a booking reads through.

A booking needs to know that the branch exists and which customer profile
belongs to the account it was asked to book for. Both are reads of tables the
identity module owns, so they sit behind ports named for that module.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.identity import Branch, CustomerProfile


class BranchRepository(Protocol):
    """Read access to the trading branches."""

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key, or None when there is none."""
        ...


class CustomerRepository(Protocol):
    """Read access to customer profiles."""

    def profile_for_account(self, user_account_id: UUID) -> CustomerProfile | None:
        """Return the customer profile that belongs to a sign in account.

        Returns:
            The profile, or None when the account has none. Staff accounts have
            none, and an account that is not a customer cannot own a booking.

        """
        ...
