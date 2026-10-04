"""The utilisation report and every refusal of it, through HTTP (FR-24, US-33, NFR-04).

These run against the in memory database. The clock stands still on Monday
the second of March 2026 at ten in the morning in Cape Town. A hire booked
for today goes out today and is due back on Thursday the fifth, and the
report is read for March unless a test says otherwise. The world's model is
hired at R185.00 a day, so three days of one unit are R555.00.

The figures here are few and worked out by hand. The full dataset with every
grouping is `tests/integration/test_report_worked_dataset.py` on PostgreSQL,
and the CSV and the dashboard are `tests/api/test_admin_report_csv_and_dashboard.py`.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.application.reporting.definitions import (
    GROSS_CONTRIBUTION_DEFINITION,
    UTILISATION_DEFINITION,
)
from app.domain.enums import UserRole
from app.infrastructure.models import Category, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.checkout_api import checked_out, confirmed_today
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.report_api import (
    FIGURE_MEMBERS,
    LINE_MEMBERS,
    REPORT_MEMBERS,
    read_admin_dashboard,
    read_csv,
    read_report,
    refused_fields,
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


class TestTheReport:
    """One page of the report, its totals and its definitions."""

    def test_a_month_with_no_hire_has_the_shape_of_the_contract(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        report = answered(read_report(booking, administrator))
        assert report.keys() == REPORT_MEMBERS
        assert (report["from"], report["to"], report["groupBy"]) == (
            "2026-03-01",
            "2026-04-01",
            "asset",
        )
        assert report["definitions"] == {
            "utilisation": UTILISATION_DEFINITION,
            "grossContribution": GROSS_CONTRIBUTION_DEFINITION,
        }
        assert report["totals"].keys() == FIGURE_MEMBERS
        assert (report["page"], report["pageSize"], report["total"]) == (1, 20, 2)
        line = report["items"][0]
        assert line.keys() == LINE_MEMBERS
        assert (line["assetCount"], line["daysOnHire"], line["serviceableDays"]) == (1, 0, 31)
        assert (line["utilisationPercent"], line["grossContribution"]) == ("0.00", "0.00")
        assert (line["branchCode"], line["status"]) == (world.branch.code, "AVAILABLE")

    def test_a_hire_of_two_units_shares_its_charge_and_counts_today(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        both_out(booking, world, assistant)
        report = answered(read_report(booking, administrator))
        for line in report["items"]:
            assert (line["daysOnHire"], line["serviceableDays"]) == (1, 31)
            assert (line["utilisationPercent"], line["hireRevenueExVat"]) == ("3.23", "555.00")
            assert line["status"] == "ON_HIRE"
        assert report["totals"]["grossContribution"] == "1110.00"
        assert report["totals"]["utilisationPercent"] == "3.23"

    def test_grouped_by_model_the_two_units_are_one_line(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        both_out(booking, world, assistant)
        report = answered(read_report(booking, administrator, groupBy="model"))
        (line,) = report["items"]
        assert (line["key"], line["label"]) == (
            world.product_model.slug,
            world.product_model.name,
        )
        assert (line["assetCount"], line["daysOnHire"], line["serviceableDays"]) == (2, 2, 62)
        assert (line["assetTag"], line["status"], line["branchCode"]) == (None, None, None)
        assert line["grossContribution"] == "1110.00"

    def test_a_page_holds_the_lines_asked_for_and_the_totals_hold_every_line(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        report = answered(read_report(booking, administrator, page=2, pageSize=1))
        assert (len(report["items"]), report["total"]) == (1, 2)
        assert report["totals"]["assetCount"] == 2

    def test_a_branch_and_a_category_narrow_the_report(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        world: BookingWorld,
        administrator: UserAccount,
    ) -> None:
        build_booking_world(factory)
        session.commit()
        category = session.get(Category, world.product_model.category_id)
        assert category is not None
        everywhere = answered(read_report(booking, administrator))
        here = answered(read_report(booking, administrator, branchCode=world.branch.code))
        in_category = answered(read_report(booking, administrator, categorySlug=category.slug))
        assert (everywhere["total"], here["total"], in_category["total"]) == (3, 2, 2)


class TestTheRefusals:
    """Each parameter a rule refuses is named, and nobody but an administrator gets in."""

    def test_a_period_with_no_start_names_from(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = booking.client.get(
            "/api/admin/reports/utilisation",
            params={"to": "2026-04-01"},
            headers=booking.headers(administrator),
        )
        assert refused_fields(response) == {"query.from"}
        assert problem_code(response) == VALIDATION_FAILURE

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"to": "2026-03-01"}, "query.to"),
            ({"to": "2027-03-03"}, "query.to"),
            ({"groupBy": "unit"}, "query.groupBy"),
            ({"pageSize": "0"}, "query.pageSize"),
            ({"pageSize": "101"}, "query.pageSize"),
            ({"page": "0"}, "query.page"),
            ({"branchCode": "ZZZ"}, "query.branchCode"),
            ({"categorySlug": "no-such-category"}, "query.categorySlug"),
        ],
    )
    def test_a_refused_parameter_is_named(
        self,
        booking: BookingClient,
        world: BookingWorld,
        administrator: UserAccount,
        params: dict[str, str],
        field: str,
    ) -> None:
        response = read_report(booking, administrator, **params)
        assert refused_fields(response) == {field}
        assert problem_code(response) == VALIDATION_FAILURE

    def test_the_csv_refuses_the_same_period_as_a_problem_document(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = read_csv(booking, administrator, to="2026-03-01")
        assert refused_fields(response) == {"query.to"}

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_anybody_but_an_administrator_is_refused(
        self, booking: BookingClient, factory: Factory, session: Session, role: UserRole
    ) -> None:
        branch = factory.branch() if role is UserRole.COUNTER_STAFF else None
        account = factory.user(role=role, branch=branch)
        session.commit()
        for response in (
            read_report(booking, account),
            read_csv(booking, account),
            read_admin_dashboard(booking, account),
        ):
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert problem_code(response) == "authorisation-failure"

    def test_a_caller_with_no_credential_is_asked_to_sign_in(self, booking: BookingClient) -> None:
        response = booking.client.get("/api/admin/dashboard")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
