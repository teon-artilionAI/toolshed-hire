"""The customers of the in memory staff store, as a change of standing reads and writes them.

The profile is built from the `CustomerSummary` the store holds for each
customer, with the standing the open transaction has given it, so a test can
see the standing change and the count of no shows stay as it was.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from app.application.identity.customer_directory import CustomerSummary
from app.domain.enums import AccountStatus
from app.domain.identity import CustomerProfile

if TYPE_CHECKING:
    from tests.support.memory_staff import StaffRecords, StaffStore


class StandingCustomers:
    """The part of the customer repository a change of standing writes through."""

    def __init__(self, store: StaffStore, working: StaffRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def get_for_update(self, customer_profile_id: UUID) -> CustomerProfile | None:
        """Return the profile with this key, with the standing this transaction gave it."""
        summary = self._store.customers.get(customer_profile_id)
        if summary is None:
            return None
        return CustomerProfile(
            id=summary.id,
            user_account_id=None,
            display_name=summary.display_name,
            account_status=self._working.standings.get(summary.id, summary.account_status),
            email=summary.email,
        )

    def save_account_status(self, customer_profile_id: UUID, status: AccountStatus) -> None:
        """Keep the new standing of a customer, inside the transaction."""
        self._working.standings[customer_profile_id] = status


class StandingDirectory:
    """The read of one customer, as the counter sees one, over the working copy."""

    def __init__(self, store: StaffStore, working: StaffRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def summary(self, customer_profile_id: UUID) -> CustomerSummary | None:
        """Return the customer with the standing this transaction gave them, if any."""
        summary = self._store.customers.get(customer_profile_id)
        if summary is None:
            return None
        standing = self._working.standings.get(summary.id, summary.account_status)
        return replace(summary, account_status=standing)


__all__ = ["StandingCustomers", "StandingDirectory"]
