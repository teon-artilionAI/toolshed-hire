"""A customer reading and editing their own details, with no database (US-05, C-26).

The profile is found by the account that asks. An edit takes the eight
contact and billing fields, all of them or none, keeps the name and the phone
number on the account as well, and writes one audit event that names the
fields and not their values. A field that may not be edited is refused by the
name the request gave it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.identity.profile import PROFILE_NOT_FOUND_MESSAGE, PROFILE_UPDATED_ACTION
from app.application.refusal import refused_parameter_of
from app.domain.account import Account
from app.domain.enums import AccountStatus
from app.domain.errors import NotFound, ValidationFailure
from tests.support.account_desk import NEW_EMAIL, AccountDesk


@pytest.fixture
def desk() -> AccountDesk:
    return AccountDesk()


@pytest.fixture
def account(desk: AccountDesk) -> Account:
    return desk.registered()


def refusal_of(desk: AccountDesk, account: Account, **changes: str | None) -> ValidationFailure:
    with pytest.raises(ValidationFailure) as refusal:
        desk.update_profile(account.id, **changes)
    return refusal.value


class TestReadingTheProfile:
    """The caller's own details, or a plain not found."""

    def test_the_profile_of_the_caller_is_returned(
        self, desk: AccountDesk, account: Account
    ) -> None:
        profile = desk.read_profile(account.id)
        assert (profile.user_account_id, profile.email) == (account.id, NEW_EMAIL)
        assert profile.account_status is AccountStatus.ACTIVE

    def test_an_account_with_no_profile_is_not_found(self, desk: AccountDesk) -> None:
        staff_like = desk.identity.add_account()
        with pytest.raises(NotFound, match=PROFILE_NOT_FOUND_MESSAGE):
            desk.read_profile(staff_like.id)
        with pytest.raises(NotFound):
            desk.read_profile(uuid4())


class TestEditingTheProfile:
    """The fields that were sent, on both rows, with one event."""

    def test_the_fields_that_were_sent_are_changed_and_the_rest_are_left(
        self, desk: AccountDesk, account: Account
    ) -> None:
        updated = desk.update_profile(account.id, billing_city="Stellenbosch", vat_number="4123")
        assert (updated.billing_city, updated.vat_number) == ("Stellenbosch", "4123")
        assert updated.billing_suburb == "Gardens"
        assert desk.read_profile(account.id).billing_city == "Stellenbosch"

    def test_the_name_and_the_phone_are_kept_on_the_account_as_well(
        self, desk: AccountDesk, account: Account
    ) -> None:
        desk.update_profile(account.id, full_name="Thandi M", phone="021 555 0101")
        stored = desk.account_for()
        assert (stored.full_name, stored.phone) == ("Thandi M", "021 555 0101")
        assert desk.read_profile(account.id).full_name == "Thandi M"

    def test_a_change_writes_one_event_naming_the_fields_and_not_the_values(
        self, desk: AccountDesk, account: Account
    ) -> None:
        desk.update_profile(account.id, billing_city="Stellenbosch", phone="021 555 0101")
        (event,) = desk.audit(PROFILE_UPDATED_ACTION)
        assert event.actor_user_id == account.id
        assert event.after_state == {"changed_fields": ["phone", "billing_city"]}
        assert "Stellenbosch" not in str(event.after_state)

    def test_an_edit_that_changes_nothing_writes_nothing(
        self, desk: AccountDesk, account: Account
    ) -> None:
        commits_before = len(desk.store.journal)
        desk.update_profile(account.id, billing_city="Cape Town")
        assert desk.audit(PROFILE_UPDATED_ACTION) == []
        assert len(desk.store.journal) == commits_before

    @pytest.mark.parametrize("field", ["account_status", "role", "trade_discount_percent"])
    def test_a_field_that_may_not_be_edited_is_refused_by_its_name_on_the_wire(
        self, desk: AccountDesk, account: Account, field: str
    ) -> None:
        refused = refusal_of(desk, account, **{field: "BLACKLISTED"})
        on_the_wire = {
            "account_status": "accountStatus",
            "role": "role",
            "trade_discount_percent": "tradeDiscountPercent",
        }[field]
        assert refused_parameter_of(refused) == on_the_wire
        assert desk.read_profile(account.id).account_status is AccountStatus.ACTIVE

    def test_a_refused_value_is_named_and_nothing_is_kept(
        self, desk: AccountDesk, account: Account
    ) -> None:
        refused = refusal_of(desk, account, full_name="Thandi M", billing_postal_code=" ")
        assert refused_parameter_of(refused) == "billingPostalCode"
        assert desk.read_profile(account.id).full_name == "Thandi Mokoena"
        assert desk.audit(PROFILE_UPDATED_ACTION) == []

    def test_an_account_with_no_profile_cannot_edit_one(self, desk: AccountDesk) -> None:
        with pytest.raises(NotFound):
            desk.update_profile(uuid4(), billing_city="Stellenbosch")
