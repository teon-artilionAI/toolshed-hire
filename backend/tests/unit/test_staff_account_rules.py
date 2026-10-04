"""The rules a staff account is kept by, with no database (FR-25, US-35, BR-43).

A staff account is counter staff with a branch or an administrator with none,
it has a name and may have a phone, and a customer's role is never one. The
last active administrator can never be deactivated or given another role, and
an administrator cannot deactivate their own account. A new account is opened
with a hash nobody knows the password of and a reset pending.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.account import Account
from app.domain.account_tokens import PendingToken
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import UserRole
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.staff_account import (
    BRANCH_NEEDED_MESSAGE,
    LAST_ADMINISTRATOR_MESSAGE,
    NO_BRANCH_FOR_ADMIN_MESSAGE,
    NOT_A_STAFF_ROLE_MESSAGE,
    OWN_ACCOUNT_MESSAGE,
    StaffDetails,
    branch_kept_for,
    checked_staff_details,
    counts_as_administrator,
    deactivated,
    details_of,
    ensure_an_administrator_remains,
    ensure_not_own_account,
    new_staff_account,
    reactivated,
    with_details,
)

NOW = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)
BRANCH = uuid4()


def details(**changes: object) -> StaffDetails:
    """Return the details of a counter assistant, with any field changed."""
    values: dict[str, object] = {
        "full_name": "  Thandi Mokoena  ",
        "phone": " 082 441 7719 ",
        "role": UserRole.COUNTER_STAFF,
        **changes,
    }
    return StaffDetails(**values)


def an_account(role: UserRole = UserRole.ADMIN, *, is_active: bool = True) -> Account:
    """Return an account in a role."""
    return Account(
        id=uuid4(),
        email=f"{uuid4().hex[:6]}@toolshedhire.co.za",
        password_hash="stand-in-hash",
        role=role,
        full_name="Wesley Adonis",
        branch_id=BRANCH if role is UserRole.COUNTER_STAFF else None,
        is_active=is_active,
    )


def refused_field(error: pytest.ExceptionInfo[ValidationFailure]) -> object:
    """Return the field a refusal names."""
    return error.value.detail[REFUSED_FIELD]


class TestTheDetails:
    """A name, a phone that may be empty, a staff role and a branch that fits it."""

    def test_the_name_and_the_phone_are_trimmed(self) -> None:
        checked = checked_staff_details(details(), has_branch=True)
        assert checked == StaffDetails(
            full_name="Thandi Mokoena", phone="082 441 7719", role=UserRole.COUNTER_STAFF
        )

    @pytest.mark.parametrize("phone", [None, "", "   "])
    def test_a_phone_left_empty_keeps_none(self, phone: str | None) -> None:
        assert checked_staff_details(details(phone=phone), has_branch=True).phone is None

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"full_name": "   "}, "full_name"),
            ({"full_name": "x" * 121}, "full_name"),
            ({"phone": "call me"}, "phone"),
            ({"phone": "0" * 21}, "phone"),
        ],
    )
    def test_a_name_or_a_phone_that_breaks_a_rule_is_refused_naming_it(
        self, changes: dict[str, object], field: str
    ) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_staff_details(details(**changes), has_branch=True)
        assert refused_field(error) == field

    def test_a_customer_role_is_refused_naming_the_role(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_staff_details(details(role=UserRole.CUSTOMER), has_branch=False)
        assert (refused_field(error), error.value.message) == ("role", NOT_A_STAFF_ROLE_MESSAGE)

    def test_counter_staff_with_no_branch_are_refused_naming_the_branch(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_staff_details(details(), has_branch=False)
        assert (refused_field(error), error.value.message) == (
            "branch_code",
            BRANCH_NEEDED_MESSAGE,
        )

    def test_an_administrator_with_a_branch_is_refused_naming_the_branch(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            checked_staff_details(details(role=UserRole.ADMIN), has_branch=True)
        assert (refused_field(error), error.value.message) == (
            "branch_code",
            NO_BRANCH_FOR_ADMIN_MESSAGE,
        )

    def test_an_administrator_with_no_branch_is_accepted(self) -> None:
        checked = checked_staff_details(details(role=UserRole.ADMIN), has_branch=False)
        assert checked.role is UserRole.ADMIN


class TestTheBranchAnEditKeeps:
    """Becoming an administrator with no branch named lets the branch go."""

    def test_an_administrator_named_no_branch_keeps_none(self) -> None:
        assert branch_kept_for(UserRole.ADMIN, BRANCH, branch_named=False) is None

    def test_a_branch_the_edit_names_is_kept_so_the_rule_can_refuse_it(self) -> None:
        assert branch_kept_for(UserRole.ADMIN, BRANCH, branch_named=True) == BRANCH

    def test_counter_staff_keep_their_branch(self) -> None:
        assert branch_kept_for(UserRole.COUNTER_STAFF, BRANCH, branch_named=False) == BRANCH


class TestTheAccount:
    """An account takes the details, and is deactivated and reactivated with its password."""

    def test_the_details_of_an_account_are_its_name_phone_and_role(self) -> None:
        account = an_account(UserRole.COUNTER_STAFF)
        assert details_of(account) == StaffDetails(
            full_name="Wesley Adonis", phone=None, role=UserRole.COUNTER_STAFF
        )

    def test_new_details_and_a_branch_replace_the_old_ones_and_nothing_else(self) -> None:
        account = an_account(UserRole.COUNTER_STAFF)
        edited = with_details(
            account,
            StaffDetails(full_name="Thandi Mokoena", phone=None, role=UserRole.ADMIN),
            None,
        )
        assert (edited.role, edited.branch_id, edited.full_name) == (
            UserRole.ADMIN,
            None,
            "Thandi Mokoena",
        )
        assert (edited.id, edited.password_hash, edited.email) == (
            account.id,
            account.password_hash,
            account.email,
        )

    def test_deactivating_and_reactivating_keep_the_password(self) -> None:
        account = an_account()
        stopped = deactivated(account)
        assert (stopped.is_active, stopped.password_hash) == (False, account.password_hash)
        assert reactivated(stopped).is_active
        assert account.is_active

    def test_deactivating_withdraws_a_reset_link_still_pending(self) -> None:
        account = an_account()
        account.start_password_reset(PendingToken.for_password_reset("made-up-token", NOW))
        assert deactivated(account).password_reset is None
        assert account.password_reset is not None

    def test_a_new_account_has_a_reset_pending_and_the_hash_it_was_given(self) -> None:
        reset = PendingToken.for_password_reset("made-up-reset-token-for-this-test", NOW)
        account = new_staff_account(
            email="thandi@toolshedhire.co.za",
            unusable_password_hash="stand-in-hash-of-a-value-nobody-kept",
            details=StaffDetails(full_name="Thandi", phone=None, role=UserRole.COUNTER_STAFF),
            branch_id=BRANCH,
            reset=reset,
        )
        assert account.password_reset == reset
        assert (account.role, account.branch_id, account.is_active) == (
            UserRole.COUNTER_STAFF,
            BRANCH,
            True,
        )
        assert account.password_hash == "stand-in-hash-of-a-value-nobody-kept"
        assert account.email_verified_at is None

    def test_only_an_active_administrator_counts(self) -> None:
        assert counts_as_administrator(an_account())
        assert not counts_as_administrator(an_account(is_active=False))
        assert not counts_as_administrator(an_account(UserRole.COUNTER_STAFF))


class TestTheLastAdministrator:
    """The last active administrator is never deactivated or given another role."""

    def test_the_last_administrator_is_not_given_another_role(self) -> None:
        last = an_account()
        demoted = with_details(last, details(), BRANCH)
        with pytest.raises(StateTransitionError) as error:
            ensure_an_administrator_remains(
                last, after=demoted, active_administrators=frozenset({last.id})
            )
        assert (error.value.message, error.value.from_status, error.value.to_status) == (
            LAST_ADMINISTRATOR_MESSAGE,
            "ADMIN",
            "COUNTER_STAFF",
        )

    def test_the_last_administrator_is_not_deactivated(self) -> None:
        last = an_account()
        with pytest.raises(StateTransitionError) as error:
            ensure_an_administrator_remains(
                last, after=deactivated(last), active_administrators=frozenset({last.id})
            )
        assert (error.value.from_status, error.value.to_status) == ("ACTIVE", "INACTIVE")

    def test_an_administrator_may_go_while_another_remains(self) -> None:
        one, other = an_account(), an_account()
        ensure_an_administrator_remains(
            one, after=deactivated(one), active_administrators=frozenset({one.id, other.id})
        )

    def test_a_change_that_keeps_the_administrator_is_never_refused(self) -> None:
        last = an_account()
        renamed = with_details(
            last, StaffDetails(full_name="Renamed", phone=None, role=UserRole.ADMIN), None
        )
        ensure_an_administrator_remains(
            last, after=renamed, active_administrators=frozenset({last.id})
        )

    def test_counter_staff_and_an_inactive_administrator_are_never_the_last(self) -> None:
        staff, idle = an_account(UserRole.COUNTER_STAFF), an_account(is_active=False)
        ensure_an_administrator_remains(
            staff, after=deactivated(staff), active_administrators=frozenset()
        )
        ensure_an_administrator_remains(
            idle, after=with_details(idle, details(), BRANCH), active_administrators=frozenset()
        )


class TestTheOwnAccount:
    """An administrator cannot deactivate their own account."""

    def test_the_own_account_is_refused(self) -> None:
        key = uuid4()
        with pytest.raises(StateTransitionError) as error:
            ensure_not_own_account(key, key)
        assert error.value.message == OWN_ACCOUNT_MESSAGE

    def test_another_account_is_allowed(self) -> None:
        ensure_not_own_account(uuid4(), uuid4())
