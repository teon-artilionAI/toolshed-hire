"""The CSV of the utilisation report and the admin dashboard, through HTTP (FR-24, US-34, C-32).

These run against the in memory database. The clock stands still on Monday
the second of March 2026 at ten in the morning in Cape Town. A hire booked
for today goes out today and is due back on Thursday the fifth, and the
report is read for March unless a test says otherwise. The world's model is
hired at R185.00 a day, so three days of one unit are R555.00.

The report itself and its refusals are in `tests/api/test_admin_reports.py`.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import AccountStatus, AssetStatus, UserRole
from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.checkout_api import checked_out, confirmed_today
from tests.support.counter_api import AFTER_CLOSING
from tests.support.factories import Factory
from tests.support.report_api import (
    BRANCH_MEMBERS,
    COUNT_MEMBERS,
    DASHBOARD_MEMBERS,
    MONTH_MEMBERS,
    read_admin_dashboard,
    read_csv,
)

UNITS: Final[int] = 2
VALIDATION_FAILURE: Final[str] = "request-validation-failure"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds two units."""
    built = build_booking_world(factory, asset_count=UNITS)
    session.commit()
    return built


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def both_out(booking: BookingClient, world: BookingWorld, assistant: UserAccount) -> None:
    """Hire both units of the world together, today, for three days."""
    reservation = confirmed_today(booking, world, assistant, quantity=UNITS)
    checked_out(booking, assistant, reservation["id"])


class TestTheCsv:
    """Every line as CSV, streamed, with the comment first and every risky cell escaped."""

    def test_the_file_is_named_and_typed_as_the_contract_says(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        response = read_csv(booking, administrator, groupBy="model")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert response.headers["content-disposition"] == (
            'attachment; filename="toolshed-gross-contribution-model-2026-03-01-2026-04-01.csv"'
        )

    def test_the_comment_comes_first_and_the_screen_columns_after_it(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        both_out(booking, world, assistant)
        lines = read_csv(booking, administrator).text.split("\r\n")
        assert lines[0].startswith('"# These are gross contribution figures and not profit.')
        assert "never profit" in lines[0]
        assert lines[1] == (
            "Asset tag,Model,Category,Branch,Status,Units,Days on hire,Serviceable days,"
            "Utilisation percent,Hire revenue ex VAT,Late fees ex VAT,Damage recovery ex VAT,"
            "Repair costs,Gross contribution"
        )
        assert lines[2].endswith(",ON_HIRE,1,1,31,3.23,555.00,0.00,0.00,0.00,555.00")
        assert (len(lines), lines[-1]) == (5, "")

    def test_a_name_a_spreadsheet_would_run_reaches_it_as_text(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        world: BookingWorld,
        administrator: UserAccount,
    ) -> None:
        risky = factory.product_model(name="=HYPERLINK(1)")
        factory.asset(product_model=risky, branch=world.branch)
        session.commit()
        body = read_csv(booking, administrator, groupBy="model").text
        assert "'=HYPERLINK(1)" in body
        assert ",=HYPERLINK" not in body


class TestTheAdminDashboard:
    """Every branch, the totals, the month so far and what waits, after the sweep."""

    def test_the_dashboard_has_the_shape_of_the_contract(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        both_out(booking, world, assistant)
        dashboard = answered(read_admin_dashboard(booking, administrator))
        assert dashboard.keys() == DASHBOARD_MEMBERS
        assert dashboard["date"] == "2026-03-02"
        (branch,) = dashboard["branches"]
        assert branch.keys() == BRANCH_MEMBERS
        assert (branch["branchCode"], branch["onHire"], branch["available"]) == (
            world.branch.code,
            2,
            0,
        )
        assert dashboard["totals"].keys() == COUNT_MEMBERS
        assert dashboard["totals"]["onHire"] == 2
        assert dashboard["monthToDate"].keys() == MONTH_MEMBERS
        assert dashboard["monthToDate"] == {
            "from": "2026-03-01",
            "to": "2026-03-03",
            "utilisationPercent": "50.00",
            "grossContribution": "1110.00",
        }

    def test_what_waits_for_an_administrator_is_counted(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        administrator: UserAccount,
    ) -> None:
        world.profile.account_status = AccountStatus.ON_HOLD
        world.assets[0].status = AssetStatus.UNDER_REPAIR
        session.add_all([world.profile, world.assets[0]])
        session.commit()
        dashboard = answered(read_admin_dashboard(booking, administrator))
        assert dashboard["customersOnHold"] == 1
        assert (dashboard["openDamageReports"], dashboard["failedNotifications"]) == (0, 0)
        assert dashboard["totals"]["underRepair"] == 1

    def test_a_booking_nobody_collected_by_closing_is_not_due(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        confirmed_today(booking, world, assistant)
        before = answered(read_admin_dashboard(booking, administrator))
        booking.clock.instant = AFTER_CLOSING
        after = answered(read_admin_dashboard(booking, administrator))
        assert (before["totals"]["collectionsDue"], after["totals"]["collectionsDue"]) == (1, 0)
