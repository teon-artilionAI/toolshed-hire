"""The in memory repositories of the reference data a booking reads.

Branches, product models and customer profiles are set up by a test and then
only read, so they live in the store and not in the working copy of a
transaction. The one exception is the count of late cancellations on a
profile (BR-16). That is a change, so it is kept in the working copy and only
survives a commit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.domain.catalogue import ProductModel
from app.domain.identity import Branch, CustomerProfile

if TYPE_CHECKING:
    from tests.support.memory import MemoryStore, Records


class MemoryBranches:
    """The branch repository."""

    def __init__(self, store: MemoryStore) -> None:
        """Bind to the store that holds the reference data."""
        self._store = store

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key, if there is one."""
        return self._store.branches.get(branch_id)

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the trading branch with this code, if there is one."""
        if code in self._store.closed_branch_codes:
            return None
        for branch in self._store.branches.values():
            if branch.code == code:
                return branch
        return None


class MemoryProductModels:
    """The product model repository."""

    def __init__(self, store: MemoryStore) -> None:
        """Bind to the store that holds the reference data."""
        self._store = store

    def get(self, product_model_id: UUID) -> ProductModel | None:
        """Return the product model with this key, if there is one."""
        return self._store.product_models.get(product_model_id)

    def find_published_by_slug(self, slug: str) -> ProductModel | None:
        """Return the published product model with this slug, if there is one."""
        if slug in self._store.unpublished_slugs:
            return None
        for model in self._store.product_models.values():
            if model.slug == slug:
                return model
        return None


class MemoryCustomers:
    """The customer repository over the working copy."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def profile_for_account(self, user_account_id: UUID) -> CustomerProfile | None:
        """Return the profile of an account, if it has one."""
        return self._store.profiles.get(user_account_id)

    def get(self, customer_profile_id: UUID) -> CustomerProfile | None:
        """Return the profile with this key, if there is one."""
        return self._store.profile_with_id(customer_profile_id)

    def record_late_cancellation(self, customer_profile_id: UUID) -> None:
        """Count one late cancellation against a profile, inside the transaction."""
        counted = self._working.late_cancellations.get(customer_profile_id, 0)
        self._working.late_cancellations[customer_profile_id] = counted + 1


__all__ = ["MemoryBranches", "MemoryCustomers", "MemoryProductModels"]
