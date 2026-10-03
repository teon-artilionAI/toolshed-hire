"""Every refusal of the repair, the close and the reads of a damage report, through HTTP.

Repair and resolution are for an administrator, so counter staff are answered
403 (US-38). A report moves only as its status allows, or it is a 409. A
report is resolved with its actual cost, or it is a 422 naming
`actualRepairCost`. A write off is refused while a booking still holds the
unit (BR-37). An unknown report is a 404, and an unknown branch on the list a
422 naming `branchCode`. Each refusal changes nothing.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest
from sqlmodel import Session

from app.domain.enums import AssetStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.checkout_api import confirmed_today
from tests.support.damage_api import (
    close_report,
    file_report,
    list_reports,
    read_report,
    refusal_of,
    refused_fields,
    report_body,
    send_for_repair,
    unit_status,
)
from tests.support.factories import Factory
from tests.support.rental_api import worked_example_world

FORBIDDEN: Final[int] = 403
NOT_FOUND: Final[int] = 404
CONFLICT: Final[int] = 409
UNKNOWN_KEY: Final[str] = "00000000-0000-4000-8000-000000000009"
RESOLVED: Final[dict[str, object]] = {"outcome": "RESOLVED", "actualRepairCost": "120.00"}
# A hire next week, which holds the unit while its report is open.
NEXT_WEEK: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of one unit."""
    return worked_example_world(session, factory)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def report(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> dict[str, object]:
    """Return an open report about the world's unit, found outside a hire."""
    body = report_body(world.assets[0].asset_tag, chargeable=False)
    return created(file_report(booking, assistant, body))


class TestOnlyAnAdministrator:
    """Counter staff may file and read a report, and may not repair or close one."""

    def test_counter_staff_are_refused_repair_and_resolution(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        session: Session,
        world: BookingWorld,
    ) -> None:
        refusal_of(send_for_repair(booking, assistant, report["id"]), FORBIDDEN)
        refusal_of(close_report(booking, assistant, report["id"], RESOLVED), FORBIDDEN)
        assert answered(read_report(booking, assistant, report["id"]))["status"] == "OPEN"
        assert unit_status(session, world.assets[0].asset_tag) is AssetStatus.QUARANTINED


class TestTheMovesOfAReport:
    """Only the moves the status allows."""

    def test_a_report_under_repair_is_not_sent_again(
        self, booking: BookingClient, administrator: UserAccount, report: dict[str, object]
    ) -> None:
        answered(send_for_repair(booking, administrator, report["id"]))
        refused = send_for_repair(booking, administrator, report["id"])
        assert "already under repair" in refusal_of(refused, CONFLICT)

    def test_a_closed_report_is_neither_repaired_nor_closed_again(
        self, booking: BookingClient, administrator: UserAccount, report: dict[str, object]
    ) -> None:
        answered(close_report(booking, administrator, report["id"], RESOLVED))
        assert "is resolved" in refusal_of(
            send_for_repair(booking, administrator, report["id"]), CONFLICT
        )
        refused = close_report(booking, administrator, report["id"], {"outcome": "WRITTEN_OFF"})
        assert "cannot be written off" in refusal_of(refused, CONFLICT)


class TestTheClose:
    """A resolution names its cost, and a write off waits for the bookings."""

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({"outcome": "RESOLVED"}, "body.actualRepairCost"),
            ({"outcome": "RESOLVED", "actualRepairCost": "-1.00"}, "body.actualRepairCost"),
            ({"outcome": "OPEN"}, "body.outcome"),
            ({"actualRepairCost": "1.00"}, "body.outcome"),
        ],
        ids=["no cost", "a negative cost", "not a close", "no outcome"],
    )
    def test_a_wrong_close_is_refused_by_its_field(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        report: dict[str, object],
        body: dict[str, object],
        field: str,
    ) -> None:
        assert field in refused_fields(close_report(booking, administrator, report["id"], body))
        assert answered(read_report(booking, administrator, report["id"]))["status"] == "OPEN"

    def test_a_write_off_is_refused_while_a_booking_holds_the_unit(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        confirmed_today(booking, world, assistant, period=NEXT_WEEK)
        tag = world.assets[0].asset_tag
        held = created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        refused = close_report(booking, administrator, held["id"], {"outcome": "WRITTEN_OFF"})
        assert "held for a booking" in refusal_of(refused, CONFLICT)
        assert answered(read_report(booking, administrator, held["id"]))["status"] == "OPEN"
        assert unit_status(session, tag) is AssetStatus.QUARANTINED


class TestUnknownReportsAndLists:
    """A report nobody filed is not found, and a list names the parameter it refused."""

    def test_an_unknown_report_is_not_found_by_every_route(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        for response in (
            read_report(booking, administrator, UNKNOWN_KEY),
            read_report(booking, administrator, "TSH-D-26-99999"),
            send_for_repair(booking, administrator, UNKNOWN_KEY),
            close_report(booking, administrator, UNKNOWN_KEY, RESOLVED),
        ):
            assert "could not find that damage report" in refusal_of(response, NOT_FOUND)

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"branchCode": "ZZZ"}, "query.branchCode"),
            ({"pageSize": 51}, "query.pageSize"),
            ({"status": "BROKEN"}, "query.status"),
        ],
    )
    def test_a_list_names_the_parameter_it_refused(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        params: dict[str, object],
        field: str,
    ) -> None:
        assert field in refused_fields(list_reports(booking, assistant, **params))
