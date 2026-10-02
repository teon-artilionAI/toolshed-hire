"""The parts of the seed and of role provisioning that need no database.

Three things are proved here. The figures of the worked example come out as
the design document states them, and stop the load if a rate changes. The seed
password is never defaulted outside development and test. And the provisioning
script refuses bad input without ever repeating a secret back.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Environment, settings
from app.domain.enums import ChargeType
from scripts.provision_roles import (
    APP_PASSWORD_VARIABLE,
    MIGRATE_PASSWORD_VARIABLE,
    OWNER_URL_VARIABLE,
    ProvisioningSettings,
    driver_url,
    read_settings,
)
from seeding import SeedDataError, SeedTally
from seeding.accounts import (
    DEVELOPMENT_SEED_PASSWORD,
    SEED_PASSWORD_VARIABLE,
    resolve_seed_password,
)
from seeding.sequences import number_of
from seeding.worked_example import compute_figures, split_vat_inclusive, vat_on

OWNER_URL = "postgresql+psycopg://owner:local_only_owner_secret@localhost:5432/toolshed_test"
APP_PASSWORD = "local_only_throwaway_app_role_password"
MIGRATE_PASSWORD = "local_only_throwaway_migrate_role_password"
BOSCH_RATES = {
    "model_name": "GBH 2-26 DRE Rotary Hammer",
    "daily_rate": Decimal("280.00"),
    "deposit_amount": Decimal("1200.00"),
    "late_fee_per_day": Decimal("120.00"),
}


class TestTheWorkedExampleFigures:
    """Four days of hire, two days late, the late fee taken from the deposit."""

    def test_the_settlement_matches_the_design_document(self) -> None:
        figures = compute_figures(**BOSCH_RATES)
        assert figures.hire_days == 4
        assert figures.days_late == 2
        assert figures.deposit_held == Decimal("1200.00")
        assert figures.deposit_withheld == Decimal("240.00")
        assert figures.deposit_refunded == Decimal("960.00")
        assert figures.balance_due == Decimal("0.00")

    def test_the_four_charges_are_the_documented_rows(self) -> None:
        rows = {
            charge.charge_type: (
                charge.amount_ex_vat,
                charge.vat_rate,
                charge.vat_amount,
                charge.amount_inc_vat,
            )
            for charge in compute_figures(**BOSCH_RATES).charges
        }
        assert rows == {
            ChargeType.HIRE: (
                Decimal("1120.00"), Decimal("15.00"), Decimal("168.00"), Decimal("1288.00")
            ),
            ChargeType.DEPOSIT_HOLD: (
                Decimal("1200.00"), Decimal("0.00"), Decimal("0.00"), Decimal("1200.00")
            ),
            ChargeType.LATE_FEE: (
                Decimal("208.70"), Decimal("15.00"), Decimal("31.30"), Decimal("240.00")
            ),
            ChargeType.DEPOSIT_RELEASE: (
                Decimal("-960.00"), Decimal("0.00"), Decimal("0.00"), Decimal("-960.00")
            ),
        }

    def test_hire_vat_is_added_on_top_and_late_fee_vat_is_taken_out(self) -> None:
        assert vat_on(Decimal("1120.00")) == Decimal("168.00")
        assert split_vat_inclusive(Decimal("240.00")) == (Decimal("208.70"), Decimal("31.30"))

    def test_a_changed_late_fee_stops_the_load_and_names_what_differs(self) -> None:
        changed = {**BOSCH_RATES, "late_fee_per_day": Decimal("150.00")}
        with pytest.raises(SeedDataError, match="deposit withheld is 300.00, expected 240.00"):
            compute_figures(**changed)


class TestTheSeedPassword:
    """The development default is never used where a real person could reach it."""

    def test_the_supplied_password_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SEED_PASSWORD_VARIABLE, "a-password-somebody-chose")
        assert resolve_seed_password() == "a-password-somebody-chose"

    def test_the_default_applies_in_test(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(SEED_PASSWORD_VARIABLE, raising=False)
        monkeypatch.setattr(settings, "environment", Environment.TEST)
        assert resolve_seed_password() == DEVELOPMENT_SEED_PASSWORD

    @pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
    def test_the_seed_refuses_to_default_outside_development_and_test(
        self, monkeypatch: pytest.MonkeyPatch, environment: Environment
    ) -> None:
        monkeypatch.delenv(SEED_PASSWORD_VARIABLE, raising=False)
        monkeypatch.setattr(settings, "environment", environment)
        with pytest.raises(RuntimeError, match=SEED_PASSWORD_VARIABLE):
            resolve_seed_password()


class TestTheSeedBookkeeping:
    """The tally and the reference numbers the sequences are moved past."""

    def test_a_run_that_only_found_rows_changed_nothing(self) -> None:
        tally = SeedTally()
        tally.record("branch", created=0, found=3)
        assert tally.changed_nothing
        assert tally.total_found == 3

    def test_a_run_that_created_a_row_changed_something(self) -> None:
        tally = SeedTally()
        tally.record("branch", created=1, found=2)
        assert not tally.changed_nothing
        assert tally.total_created == 1

    def test_a_negative_count_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            SeedTally().record("branch", created=-1, found=0)

    def test_the_number_of_a_reference_is_its_last_part(self) -> None:
        assert number_of("TSH-R-26-000123") == 123
        assert number_of("TSH-H-26-000098") == 98

    def test_a_reference_with_no_number_is_refused(self) -> None:
        with pytest.raises(SeedDataError, match="does not end in a number"):
            number_of("TSH-R-26-DRAFT")


class TestRoleProvisioningInput:
    """The script fails fast on bad input and never repeats a secret."""

    def test_a_sqlalchemy_url_is_rewritten_for_the_driver(self) -> None:
        assert driver_url(OWNER_URL) == OWNER_URL.replace("postgresql+psycopg://", "postgresql://")

    def test_a_plain_postgres_url_is_left_alone(self) -> None:
        assert driver_url("postgresql://owner@localhost/toolshed") == (
            "postgresql://owner@localhost/toolshed"
        )

    def test_a_url_for_another_database_is_refused_without_echoing_it(self) -> None:
        with pytest.raises(ValueError, match="scheme 'mysql'") as caught:
            driver_url("mysql://owner:local_only_owner_secret@localhost/toolshed")
        assert "local_only_owner_secret" not in str(caught.value)

    @pytest.mark.parametrize(
        "missing", [OWNER_URL_VARIABLE, APP_PASSWORD_VARIABLE, MIGRATE_PASSWORD_VARIABLE]
    )
    def test_a_missing_variable_is_named(
        self, monkeypatch: pytest.MonkeyPatch, missing: str
    ) -> None:
        monkeypatch.setenv(OWNER_URL_VARIABLE, OWNER_URL)
        monkeypatch.setenv(APP_PASSWORD_VARIABLE, APP_PASSWORD)
        monkeypatch.setenv(MIGRATE_PASSWORD_VARIABLE, MIGRATE_PASSWORD)
        monkeypatch.delenv(missing)
        with pytest.raises(ValueError, match=f"{missing} is not set") as caught:
            read_settings()
        assert "local_only" not in str(caught.value)

    def test_the_settings_never_show_their_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(OWNER_URL_VARIABLE, OWNER_URL)
        monkeypatch.setenv(APP_PASSWORD_VARIABLE, APP_PASSWORD)
        monkeypatch.setenv(MIGRATE_PASSWORD_VARIABLE, MIGRATE_PASSWORD)
        loaded = read_settings()
        assert isinstance(loaded, ProvisioningSettings)
        assert loaded.owner_url.startswith("postgresql://")
        assert "local_only" not in repr(loaded)
