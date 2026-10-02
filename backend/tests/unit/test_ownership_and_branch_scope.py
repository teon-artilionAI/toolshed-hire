"""The two reusable authorisation rules, with nothing around them (BR-42, BR-43).

The scope a read runs under and the branch a write may be aimed at. Both are
decided from the actor alone, so both can be pinned without a database. What
the scope does to a query is proved against SQL in
tests/api/test_ownership_and_branch_scope.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.ownership import not_found, owner_scope_for
from app.domain.enums import UserRole
from app.domain.errors import BranchScopeError
from app.domain.identity import Actor, ensure_branch_scope


class TestTheScopeOfARead:
    """A customer reads their own records. Staff read anybody's."""

    def test_a_customer_is_limited_to_their_own_account(self) -> None:
        customer = Actor(user_id=uuid4(), role=UserRole.CUSTOMER)
        scope = owner_scope_for(customer)
        assert scope.customer_user_id == customer.user_id
        assert scope.is_restricted

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.ADMIN])
    def test_staff_are_not_limited_by_owner(self, role: UserRole) -> None:
        scope = owner_scope_for(Actor(user_id=uuid4(), role=role, branch_id=None))
        assert scope.customer_user_id is None
        assert not scope.is_restricted

    def test_the_refusal_names_the_key_and_says_nothing_about_an_owner(self) -> None:
        reservation_id = uuid4()
        refusal = not_found("reservation", reservation_id)
        assert refusal.code == "not-found"
        assert refusal.detail == {"reservation_id": str(reservation_id)}
        assert "owner" not in refusal.message
        assert "belong" not in refusal.message


class TestTheBranchAWriteMayBeAimedAt:
    """Counter staff write to their own branch and to no other."""

    def test_counter_staff_may_write_to_their_own_branch(self) -> None:
        branch_id = uuid4()
        assistant = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=branch_id)
        ensure_branch_scope(assistant, branch_id)

    def test_counter_staff_are_refused_at_another_branch(self) -> None:
        other_branch = uuid4()
        assistant = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=uuid4())
        with pytest.raises(BranchScopeError) as refusal:
            ensure_branch_scope(assistant, other_branch)
        assert refusal.value.code == "branch-scope"
        assert refusal.value.detail == {"branch_id": str(other_branch)}

    def test_a_counter_actor_built_with_no_branch_is_refused_everywhere(self) -> None:
        unscoped = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF)
        with pytest.raises(BranchScopeError):
            ensure_branch_scope(unscoped, uuid4())

    @pytest.mark.parametrize("role", [UserRole.CUSTOMER, UserRole.ADMIN])
    def test_a_customer_and_an_administrator_are_not_branch_scoped(self, role: UserRole) -> None:
        ensure_branch_scope(Actor(user_id=uuid4(), role=role), uuid4())
