"""Deactivating and reactivating a staff account, and reading the staff, against ports (US-35).

A deactivation stops the account and revokes every refresh session it holds
with `ADMIN_REVOKE`, in one transaction, with the reason in the audit event.
The last active administrator is never deactivated and nobody deactivates
their own account. A reactivation lets the account sign in with the password
it had. Asking for the state an account is in writes nothing. The list of
staff refuses a customer's role naming it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.identity.staff_changes import (
    STAFF_DEACTIVATED_ACTION,
    STAFF_REACTIVATED_ACTION,
)
from app.application.identity.staff_read_models import StaffSearch
from app.application.identity.staff_reads import ReadStaff, StaffListRequest
from app.application.refusal import refused_parameter_of
from app.domain.enums import RevokeReason, UserRole
from app.domain.errors import (
    AuthorisationFailure,
    NotFound,
    StateTransitionError,
    ValidationFailure,
)
from app.domain.identity import Actor
from app.domain.staff_account import OWN_ACCOUNT_MESSAGE
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory_staff import MemoryStaffDirectory, StoreFault
from tests.support.staff_desk import StaffDesk, staff_desk


@pytest.fixture
def desk() -> StaffDesk:
    """Return a store with three branches and two administrators."""
    return staff_desk()


class TestDeactivating:
    """The account stops at once and every session it holds is revoked."""

    def test_the_account_is_stopped_and_its_sessions_revoked_with_the_reason(
        self, desk: StaffDesk
    ) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        first, second = desk.store.open_session(staff), desk.store.open_session(staff)
        other = desk.store.open_session(desk.owner)
        member = desk.deactivate(staff, reason="  Left the business.  ")
        assert member.is_active is False
        sessions = desk.store.committed.sessions
        assert {sessions[s.id].revoked_reason for s in (first, second)} == {
            RevokeReason.ADMIN_REVOKE
        }
        assert {sessions[s.id].revoked_at for s in (first, second)} == {DEFAULT_INSTANT}
        assert sessions[other.id].revoked_at is None
        event = desk.store.events[-1]
        assert (event.action, event.before_state, event.after_state) == (
            STAFF_DEACTIVATED_ACTION,
            {"is_active": True},
            {
                "is_active": False,
                "reason": "Left the business.",
                "revoked_session_count": 2,
                "revoke_reason": "ADMIN_REVOKE",
                "reset_link_withdrawn": False,
            },
        )
        assert desk.store.account(staff.id).password_hash == staff.password_hash

    def test_a_reset_link_still_pending_stops_working(self, desk: StaffDesk) -> None:
        opened = desk.open()
        assert desk.store.account(opened.member.id).password_reset is not None
        stopped = desk.store.account(opened.member.id)
        desk.deactivate(stopped)
        assert desk.store.account(opened.member.id).password_reset is None
        assert desk.store.events[-1].after_state is not None
        assert desk.store.events[-1].after_state["reset_link_withdrawn"] is True

    def test_an_administrator_may_be_deactivated_while_another_remains(
        self, desk: StaffDesk
    ) -> None:
        assert desk.deactivate(desk.bookkeeper).is_active is False

    def test_nobody_can_deactivate_the_last_active_administrator(self, desk: StaffDesk) -> None:
        desk.deactivate(desk.bookkeeper)
        with pytest.raises(AuthorisationFailure):
            desk.deactivate(desk.owner, actor=desk.bookkeeper)
        with pytest.raises(StateTransitionError) as error:
            desk.deactivate(desk.owner, actor=desk.owner)
        assert error.value.message == OWN_ACCOUNT_MESSAGE
        assert desk.store.account(desk.owner.id).is_active is True

    def test_an_administrator_cannot_deactivate_their_own_account(self, desk: StaffDesk) -> None:
        with pytest.raises(StateTransitionError) as error:
            desk.deactivate(desk.owner, actor=desk.owner)
        assert error.value.message == OWN_ACCOUNT_MESSAGE
        assert desk.store.journal == []

    def test_a_deactivated_account_asked_again_writes_nothing(self, desk: StaffDesk) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD", is_active=False)
        assert desk.deactivate(staff).is_active is False
        assert desk.store.journal == []

    @pytest.mark.parametrize("reason", ["", "   ", "Gone", "x" * 201])
    def test_a_reason_out_of_bounds_is_refused_naming_it(
        self, desk: StaffDesk, reason: str
    ) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        with pytest.raises(ValidationFailure) as error:
            desk.deactivate(staff, reason=reason)
        assert refused_parameter_of(error.value) == "reason"
        assert desk.store.journal == []

    def test_an_audit_event_that_cannot_be_written_keeps_the_account_and_its_sessions(
        self, desk: StaffDesk
    ) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        session = desk.store.open_session(staff)
        desk.store.fail_audit = True
        with pytest.raises(StoreFault):
            desk.deactivate(staff)
        assert desk.store.account(staff.id).is_active is True
        assert desk.store.committed.sessions[session.id].revoked_at is None

    def test_a_customer_account_is_not_found(self, desk: StaffDesk) -> None:
        with pytest.raises(NotFound):
            desk.deactivate(desk.store.keep(role=UserRole.CUSTOMER))

    def test_an_actor_who_is_no_longer_an_administrator_is_refused(self, desk: StaffDesk) -> None:
        idle = desk.store.keep(role=UserRole.ADMIN, is_active=False)
        with pytest.raises(AuthorisationFailure):
            desk.deactivate(desk.bookkeeper, actor=idle)


class TestReactivating:
    """A deactivated account signs in again with the password it had."""

    def test_the_account_is_active_again_and_recorded(self, desk: StaffDesk) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD", is_active=False)
        member = desk.reactivate(staff)
        assert member.is_active is True
        assert desk.store.account(staff.id).password_hash == staff.password_hash
        event = desk.store.events[-1]
        assert (event.action, event.before_state, event.after_state) == (
            STAFF_REACTIVATED_ACTION,
            {"is_active": False},
            {"is_active": True},
        )

    def test_an_active_account_asked_again_writes_nothing(self, desk: StaffDesk) -> None:
        assert desk.reactivate(desk.bookkeeper).is_active is True
        assert desk.store.journal == []

    def test_a_key_nobody_issued_is_not_found(self, desk: StaffDesk) -> None:
        stranger = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        desk.store.committed.accounts.pop(stranger.id)
        with pytest.raises(NotFound):
            desk.reactivate(stranger)


class TestReadingTheStaff:
    """The list holds staff only and refuses a customer's role naming it."""

    def request(self, **changes: object) -> StaffListRequest:
        """Return a request for the first page, with any field changed."""
        values: dict[str, object] = {
            "actor": Actor(user_id=uuid4(), role=UserRole.ADMIN),
            "text": None,
            "role": None,
            "active": None,
            "page": 1,
            "page_size": 20,
            **changes,
        }
        return StaffListRequest(**values)

    def test_the_staff_are_listed_by_name_without_customers(self, desk: StaffDesk) -> None:
        desk.store.keep(role=UserRole.CUSTOMER, full_name="Aaron Customer")
        desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="BLV", full_name="Bongani")
        page = ReadStaff(MemoryStaffDirectory(desk.store)).page(self.request())
        assert [member.full_name for member in page.items] == [
            "Anne Kleynhans",
            "Bongani",
            "Pieter Kleynhans",
        ]
        assert page.items[1].branch_code == "BLV"
        counter = ReadStaff(MemoryStaffDirectory(desk.store)).page(
            self.request(role=UserRole.COUNTER_STAFF, active=True)
        )
        assert counter.total == 1

    def test_a_customer_role_is_refused_naming_the_parameter(self, desk: StaffDesk) -> None:
        with pytest.raises(ValidationFailure) as error:
            ReadStaff(MemoryStaffDirectory(desk.store)).page(
                self.request(role=UserRole.CUSTOMER)
            )
        assert refused_parameter_of(error.value) == "role"

    @pytest.mark.parametrize(
        "changes",
        [{"text": "a"}, {"text": "x" * 81}, {"page": 0}, {"page_size": 0}, {"page_size": 101}],
    )
    def test_a_search_out_of_range_cannot_be_built(self, changes: dict[str, object]) -> None:
        values: dict[str, object] = {
            "text": None,
            "role": None,
            "active": None,
            "page": 1,
            "page_size": 20,
            **changes,
        }
        with pytest.raises(ValueError, match="Attempted to"):
            StaffSearch(**values)

    def test_a_search_says_how_many_come_before_its_page(self) -> None:
        search = StaffSearch(text="th", role=None, active=None, page=3, page_size=20)
        assert search.offset == 40
