"""Opening a staff account and editing one, run against ports and nothing else (FR-25, US-35).

A new account is opened with a hash of a value nobody kept and a reset token,
and the person is sent the reset link every account uses, so nobody reads or
sets a password. The answer says whether the gateway took the message. An
edit changes the name, the phone, the role and the branch it names, lets go
of the branch when somebody becomes an administrator, never demotes the last
active administrator, and writes nothing when it changes nothing. Every write
first locks the administrators and refuses an actor who is no longer one, and
a refused write, or one whose audit event fails, commits nothing.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.application.catalogue.admin_commands import Change
from app.application.identity.staff_accounts import EMAIL_TAKEN_MESSAGE
from app.application.identity.staff_changes import (
    NO_LONGER_ADMINISTRATOR_MESSAGE,
    STAFF_OPENED_ACTION,
    STAFF_UPDATED_ACTION,
)
from app.application.identity.staff_commands import StaffChanges
from app.application.refusal import refused_parameter_of
from app.domain.account_tokens import hash_account_token
from app.domain.enums import UserRole
from app.domain.errors import (
    AuthorisationFailure,
    NotFound,
    StateTransitionError,
    ValidationFailure,
)
from app.domain.staff_account import LAST_ADMINISTRATOR_MESSAGE
from app.infrastructure.notification import FakeEmailGateway
from tests.support.memory_staff import StoreFault
from tests.support.staff_desk import NEW_EMAIL, ORIGIN, StaffDesk, staff_desk

RESET_LINK_PREFIX = f"{ORIGIN}/signin#reset="


@pytest.fixture
def desk() -> StaffDesk:
    """Return a store with three branches and two administrators."""
    return staff_desk()


def refused_name(error: pytest.ExceptionInfo[ValidationFailure]) -> str | None:
    """Return the field a refusal names on the wire."""
    return refused_parameter_of(error.value)


class TestOpeningAnAccount:
    """An account is opened with no password anyone knows and a link to choose one."""

    def test_the_account_is_opened_with_a_reset_pending_and_recorded(
        self, desk: StaffDesk
    ) -> None:
        opened = desk.open(email="  Thandi.Mokoena@ToolshedHire.co.za ")
        member = opened.member
        assert (member.email, member.role, member.branch_code, member.is_active) == (
            NEW_EMAIL,
            UserRole.COUNTER_STAFF,
            "CBD",
            True,
        )
        stored = desk.store.account(member.id)
        assert stored.password_reset is not None
        assert stored.password_hash.startswith("stand-in-hash-of:")
        assert desk.hasher.call_count == 1
        event = desk.store.events[-1]
        assert (event.action, event.entity_type, event.entity_id) == (
            STAFF_OPENED_ACTION,
            "user_account",
            member.id,
        )
        assert event.after_state == {
            "role": "COUNTER_STAFF",
            "branch_code": "CBD",
            "is_active": True,
            "reset_link_issued": True,
        }
        assert desk.store.locks_asked == 1

    def test_the_person_is_sent_the_reset_link_that_redeems_the_stored_token(
        self, desk: StaffDesk
    ) -> None:
        opened = desk.open()
        (message,) = desk.gateway.sent_to(NEW_EMAIL)
        link = next(line for line in message.text_body.splitlines() if RESET_LINK_PREFIX in line)
        token = link.removeprefix(RESET_LINK_PREFIX)
        pending = desk.store.account(opened.member.id).password_reset
        assert pending is not None
        assert pending.token_hash == hash_account_token(token)
        assert token not in desk.store.account(opened.member.id).password_hash
        assert opened.email_deliverable is True

    def test_a_message_the_gateway_refused_is_answered_as_not_deliverable(
        self, desk: StaffDesk
    ) -> None:
        desk.gateway = FakeEmailGateway(failure_reason="The provider is down.")
        opened = desk.open()
        assert opened.email_deliverable is False
        assert desk.store.account(opened.member.id).password_reset is not None

    def test_an_administrator_is_opened_with_no_branch(self, desk: StaffDesk) -> None:
        opened = desk.open(role=UserRole.ADMIN, branch_code=None, phone=None)
        assert (opened.member.role, opened.member.branch_code, opened.member.phone) == (
            UserRole.ADMIN,
            None,
            None,
        )

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"role": UserRole.CUSTOMER, "branch_code": None}, "role"),
            ({"branch_code": None}, "branchCode"),
            ({"role": UserRole.ADMIN}, "branchCode"),
            ({"branch_code": "XYZ"}, "branchCode"),
            ({"full_name": " "}, "fullName"),
            ({"phone": "ring me"}, "phone"),
        ],
    )
    def test_a_field_that_breaks_a_rule_is_refused_naming_it_and_nothing_is_kept(
        self, desk: StaffDesk, changes: dict[str, object], field: str
    ) -> None:
        with pytest.raises(ValidationFailure) as error:
            desk.open(**changes)
        assert refused_name(error) == field
        assert desk.store.journal == []

    def test_a_branch_that_stopped_trading_is_refused(self, desk: StaffDesk) -> None:
        desk.store.closed_branch_codes.add("BLV")
        with pytest.raises(ValidationFailure) as error:
            desk.open(branch_code="BLV")
        assert refused_name(error) == "branchCode"

    def test_an_address_another_account_holds_is_refused_naming_it(self, desk: StaffDesk) -> None:
        desk.store.keep(role=UserRole.CUSTOMER, email=NEW_EMAIL)
        with pytest.raises(ValidationFailure) as error:
            desk.open(email=NEW_EMAIL.upper())
        assert (refused_name(error), error.value.message) == ("email", EMAIL_TAKEN_MESSAGE)
        assert desk.gateway.sent == []

    def test_an_address_taken_in_a_race_is_refused_the_same_way(self, desk: StaffDesk) -> None:
        desk.store.address_taken_at_write = True
        with pytest.raises(ValidationFailure) as error:
            desk.open()
        assert (refused_name(error), error.value.message) == ("email", EMAIL_TAKEN_MESSAGE)
        assert desk.store.journal == []

    def test_an_actor_who_is_no_longer_an_administrator_is_refused(self, desk: StaffDesk) -> None:
        demoted = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        with pytest.raises(AuthorisationFailure) as error:
            desk.open(actor=demoted)
        assert error.value.message == NO_LONGER_ADMINISTRATOR_MESSAGE
        assert desk.store.journal == []

    def test_an_audit_event_that_cannot_be_written_keeps_nothing_and_sends_nothing(
        self, desk: StaffDesk
    ) -> None:
        desk.store.fail_audit = True
        with pytest.raises(StoreFault):
            desk.open()
        assert desk.store.journal == []
        assert desk.gateway.sent == []

    def test_an_account_that_cannot_be_read_back_is_a_fault(self, desk: StaffDesk) -> None:
        desk.store.forget_answers = True
        with pytest.raises(LookupError):
            desk.open()


class TestEditingAnAccount:
    """An edit changes what it names, and the role and branch rules hold after it."""

    def test_the_name_and_the_phone_change_and_are_recorded_by_name_only(
        self, desk: StaffDesk
    ) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        member = desk.edit(
            staff, StaffChanges(full_name=Change("Thandi M."), phone=Change("021 555 0101"))
        )
        assert (member.full_name, member.phone) == ("Thandi M.", "021 555 0101")
        event = desk.store.events[-1]
        assert event.action == STAFF_UPDATED_ACTION
        assert (event.before_state, event.after_state) == (
            {},
            {"changed_fields": ["full_name", "phone"]},
        )

    def test_a_move_to_another_branch_records_both_codes(self, desk: StaffDesk) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        member = desk.edit(staff, StaffChanges(branch_code=Change("BLV")))
        assert member.branch_code == "BLV"
        event = desk.store.events[-1]
        assert (event.before_state, event.after_state) == (
            {"branch_code": "CBD"},
            {"changed_fields": ["branch_code"], "branch_code": "BLV"},
        )

    def test_becoming_an_administrator_lets_the_branch_go(self, desk: StaffDesk) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="SMW")
        member = desk.edit(staff, StaffChanges(role=Change(UserRole.ADMIN)))
        assert (member.role, member.branch_code) == (UserRole.ADMIN, None)
        assert desk.store.events[-1].after_state == {
            "changed_fields": ["branch_code", "role"],
            "role": "ADMIN",
            "branch_code": None,
        }

    def test_an_administrator_moved_to_the_counter_needs_a_branch(self, desk: StaffDesk) -> None:
        with pytest.raises(ValidationFailure) as error:
            desk.edit(desk.bookkeeper, StaffChanges(role=Change(UserRole.COUNTER_STAFF)))
        assert refused_name(error) == "branchCode"
        member = desk.edit(
            desk.bookkeeper,
            StaffChanges(role=Change(UserRole.COUNTER_STAFF), branch_code=Change("CBD")),
        )
        assert (member.role, member.branch_code) == (UserRole.COUNTER_STAFF, "CBD")

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            (StaffChanges(branch_code=Change(None)), "branchCode"),
            (StaffChanges(role=Change(UserRole.CUSTOMER)), "role"),
            (StaffChanges(full_name=Change("")), "fullName"),
            (StaffChanges(branch_code=Change("NOPE")), "branchCode"),
        ],
    )
    def test_an_edit_that_breaks_a_rule_is_refused_naming_the_field(
        self, desk: StaffDesk, changes: StaffChanges, field: str
    ) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        with pytest.raises(ValidationFailure) as error:
            desk.edit(staff, changes)
        assert refused_name(error) == field
        assert desk.store.journal == []

    def test_naming_a_branch_for_an_administrator_is_refused(self, desk: StaffDesk) -> None:
        with pytest.raises(ValidationFailure) as error:
            desk.edit(desk.bookkeeper, StaffChanges(branch_code=Change("CBD")))
        assert refused_name(error) == "branchCode"

    def test_the_last_active_administrator_is_never_given_another_role(
        self, desk: StaffDesk
    ) -> None:
        desk.deactivate(desk.bookkeeper)
        with pytest.raises(StateTransitionError) as error:
            desk.edit(
                desk.owner,
                StaffChanges(role=Change(UserRole.COUNTER_STAFF), branch_code=Change("CBD")),
            )
        assert error.value.message == LAST_ADMINISTRATOR_MESSAGE
        assert desk.store.account(desk.owner.id).role is UserRole.ADMIN

    def test_an_administrator_may_step_down_while_another_remains(self, desk: StaffDesk) -> None:
        member = desk.edit(
            desk.owner,
            StaffChanges(role=Change(UserRole.COUNTER_STAFF), branch_code=Change("CBD")),
        )
        assert member.role is UserRole.COUNTER_STAFF

    def test_an_edit_that_changes_nothing_writes_nothing(self, desk: StaffDesk) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        member = desk.edit(staff, StaffChanges(full_name=Change(staff.full_name)))
        assert member.id == staff.id
        assert desk.store.journal == []

    def test_a_customer_account_or_a_key_nobody_issued_is_not_found(
        self, desk: StaffDesk
    ) -> None:
        customer = desk.store.keep(role=UserRole.CUSTOMER)
        with pytest.raises(NotFound):
            desk.edit(customer, StaffChanges(full_name=Change("Somebody")))
        stranger = desk.store.keep(role=UserRole.CUSTOMER)
        desk.store.committed.accounts.pop(stranger.id)
        with pytest.raises(NotFound):
            desk.edit(stranger, StaffChanges(full_name=Change("Nobody")))

    def test_a_branch_that_no_longer_exists_reads_as_no_code_in_the_event(
        self, desk: StaffDesk
    ) -> None:
        staff = desk.store.keep(role=UserRole.COUNTER_STAFF, branch_code="CBD")
        desk.store.committed.accounts[staff.id] = replace(staff, branch_id=uuid4())
        desk.edit(staff, StaffChanges(branch_code=Change("BLV")))
        assert desk.store.events[-1].before_state == {"branch_code": None}

    def test_an_actor_who_is_no_longer_an_administrator_changes_nothing(
        self, desk: StaffDesk
    ) -> None:
        desk.deactivate(desk.bookkeeper)
        with pytest.raises(AuthorisationFailure):
            desk.edit(desk.owner, StaffChanges(full_name=Change("X")), actor=desk.bookkeeper)
