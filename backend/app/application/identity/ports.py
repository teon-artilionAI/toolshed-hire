"""The identity ports a booking reads through, and the branch directory.

A booking needs to know that the branch exists and which customer profile
belongs to the account it was asked to book for. Both are reads of tables the
identity module owns, so they sit behind ports named for that module.

The branch directory is the read side of the same module. It lists the trading
branches for a visitor, and an availability search uses it to check the branch
it was asked about.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.identity.read_models import BranchListing
from app.domain.identity import Branch, CustomerProfile


class BranchDirectory(Protocol):
    """The trading branches, as a visitor may see them."""

    def list_active(self) -> list[BranchListing]:
        """Return every active branch, ordered by name and then by code."""
        ...


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
