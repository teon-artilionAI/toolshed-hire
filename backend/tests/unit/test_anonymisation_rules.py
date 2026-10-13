"""The values an anonymised customer is given, and when one may be anonymised (#113).

Every value fits its column and names nobody, and the address of an account is
unique to its profile and can never deliver. A customer anonymised already is
refused, and so is one with anything open, in a sentence that names what. The
job's two years are calendar years, leap day included.

The SQL side is held against the personal data map here too. Every column the
map names as identifying the profile or the account is written over, and every
free text column it lists on a customer's own rows, but the audit trail's, is
given a treatment. A column added to the map later fails this until the
anonymisation decides what to do with it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.anonymisation import (
    ALREADY_ANONYMISED_MESSAGE,
    ANONYMISED_DISPLAY_NAME,
    AnonymisedProfile,
    OpenMatters,
    anonymised_account,
    anonymised_email,
    anonymised_profile,
    dormancy_cutoff,
    ensure_may_be_anonymised,
    ensure_still_dormant,
)
from app.domain.enums import CustomerType
from app.domain.errors import StateTransitionError
from app.infrastructure.models import CustomerProfile, UserAccount
from app.infrastructure.personal_data import (
    ACCOUNT_COLUMNS,
    FREE_TEXT_TREATMENT,
    PROFILE_COLUMNS,
    SESSION_COLUMNS,
)
from app.infrastructure.personal_data_map import PERSONAL_DATA_MAP, CustomerData

NOW = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)
# The audit trail is append only for the application role (BR-49).
NEVER_TOUCHED = "audit_event"


def identifying(table: str) -> set[str]:
    """Return the columns the map names as identifying in one table."""
    kind = PERSONAL_DATA_MAP[table]
    assert isinstance(kind, CustomerData)
    return set(kind.identifying_columns)


class TestTheValues:
    """What an anonymised profile and account hold."""

    @pytest.mark.parametrize("customer_type", list(CustomerType))
    def test_every_value_fits_its_column(self, customer_type: CustomerType) -> None:
        values = anonymised_profile(customer_type)
        for name, value in vars_of(values).items():
            column = CustomerProfile.__table__.columns[name]
            if value is None:
                assert column.nullable, name
            else:
                assert len(value) <= column.type.length, name

    def test_a_trade_customer_keeps_a_company_and_an_individual_has_none(self) -> None:
        assert anonymised_profile(CustomerType.TRADE).company_name == ANONYMISED_DISPLAY_NAME
        assert anonymised_profile(CustomerType.INDIVIDUAL).company_name is None

    def test_the_address_is_unique_to_the_profile_and_never_delivers(self) -> None:
        first, second = uuid4(), uuid4()
        assert anonymised_email(first) != anonymised_email(second)
        assert anonymised_email(first).endswith(".invalid")
        account = anonymised_account(first)
        assert (account.full_name, account.phone) == (ANONYMISED_DISPLAY_NAME, None)


class TestWhoMayBeAnonymised:
    """Once only, and with nothing open."""

    def test_a_customer_with_nothing_open_may_be(self) -> None:
        ensure_may_be_anonymised(None, OpenMatters())

    def test_a_customer_anonymised_already_is_refused(self) -> None:
        with pytest.raises(StateTransitionError) as refused:
            ensure_may_be_anonymised(NOW, OpenMatters())
        assert refused.value.message == ALREADY_ANONYMISED_MESSAGE

    @pytest.mark.parametrize(
        ("matters", "named"),
        [
            (OpenMatters(open_bookings=1), "a booking still open"),
            (OpenMatters(open_bookings=2), "2 bookings still open"),
            (OpenMatters(unsettled_hires=1), "a hire not yet settled"),
            (OpenMatters(hires_owing=3), "money owing on 3 hires"),
            (
                OpenMatters(open_bookings=1, unsettled_hires=2, hires_owing=1),
                "a booking still open, 2 hires not yet settled and money owing on a hire",
            ),
        ],
    )
    def test_anything_open_refuses_naming_it(self, matters: OpenMatters, named: str) -> None:
        with pytest.raises(StateTransitionError) as refused:
            ensure_may_be_anonymised(None, matters)
        assert refused.value.message == (
            f"This customer still has {named}, so their details cannot be removed yet. "
            "Finish what is open first."
        )

    def test_an_account_that_signed_in_since_the_cutoff_is_not_dormant(self) -> None:
        cutoff = dormancy_cutoff(NOW)
        ensure_still_dormant(None, cutoff)
        ensure_still_dormant(cutoff.replace(year=cutoff.year - 1), cutoff)
        with pytest.raises(StateTransitionError):
            ensure_still_dormant(cutoff, cutoff)


class TestTheCutoff:
    """Two calendar years before the run."""

    def test_it_is_the_same_instant_two_years_before(self) -> None:
        assert dormancy_cutoff(NOW) == datetime(2024, 10, 13, 9, 30, tzinfo=UTC)

    def test_a_leap_day_becomes_the_twenty_eighth(self) -> None:
        leap_day = datetime(2028, 2, 29, 2, 0, tzinfo=UTC)
        assert dormancy_cutoff(leap_day) == datetime(2026, 2, 28, 2, 0, tzinfo=UTC)


class TestTheMapIsCovered:
    """The SQL side writes over every column the personal data map names."""

    def test_every_identifying_column_of_the_profile_is_written_over(self) -> None:
        assert set(PROFILE_COLUMNS) == identifying("customer_profile")

    def test_every_identifying_column_of_the_account_is_written_over(self) -> None:
        assert identifying("user_account") <= set(ACCOUNT_COLUMNS)
        assert set(ACCOUNT_COLUMNS) <= set(UserAccount.__table__.columns.keys())

    def test_the_browser_and_address_of_every_session_are_cleared(self) -> None:
        assert set(SESSION_COLUMNS) == identifying("refresh_session")

    def test_every_free_text_column_but_the_audit_trails_has_a_treatment(self) -> None:
        listed = {
            (table, column)
            for table, kind in PERSONAL_DATA_MAP.items()
            if isinstance(kind, CustomerData) and table != NEVER_TOUCHED
            for column in kind.free_text_columns
        }
        assert set(FREE_TEXT_TREATMENT) == listed


def vars_of(values: AnonymisedProfile) -> dict[str, str | None]:
    """Return the values of an anonymised profile by column name."""
    return {name: getattr(values, name) for name in PROFILE_COLUMNS}
