"""Quarantine at return, and filing, reading, repairing and closing damage reports, through HTTP.

A unit that comes back a grade worse, or flagged, goes to quarantine and the
deposit of its hire waits for the report (BR-35). A report records the
decision on the charge, takes the unit out of availability and, once closed,
puts it back on the shelf or retires it (BR-38). These run against the in
memory database on a clock that stands still on Monday the second of March
2026. The whole path from checkout to a settled deposit is in
tests/api/test_damage_journey.py, and the refusals are in
tests/api/test_damage_report_refusals.py and tests/api/test_damage_close_refusals.py.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Final
from uuid import UUID

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import Asset, AuditEvent, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.checkout_api import read_rental
from tests.support.damage_api import (
    REPORT_MEMBERS,
    close_report,
    file_report,
    list_reports,
    only_item,
    read_report,
    report_body,
    returned_worse,
    send_for_repair,
    unit_status,
)
from tests.support.factories import Factory
from tests.support.rental_api import (
    charges_of,
    item_ids,
    on_hire,
    return_body,
    take_back,
    worked_example_world,
)

REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^TSH-D-26-\d{5}$")
TWO_UNITS: Final[int] = 2
TWO_REPORTS: Final[int] = 2
FIVE_MINUTES: Final[timedelta] = timedelta(minutes=5)


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units with the deposit of the worked example."""
    return worked_example_world(session, factory, units=TWO_UNITS)


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


class TestAReturnThatQuarantines:
    """A worse grade or the flag sends the unit to quarantine and the deposit waits."""

    def test_a_unit_back_a_grade_worse_is_quarantined_and_the_deposit_waits(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        back = returned_worse(booking, world, assistant)
        item = only_item(back)
        assert (item["conditionIn"], item["damageAssessment"]) == ("B", "REQUIRED")
        assert (back["status"], back["settlementWaitingOn"]) == ("RETURNED", "DAMAGE_ASSESSMENT")
        assert (back["depositRefunded"], back["settledAt"]) == ("0.00", None)
        assert unit_status(session, item["assetTag"]) is AssetStatus.QUARANTINED

    def test_a_flagged_unit_in_the_same_grade_is_quarantined_and_stays_waiting(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        rental = on_hire(booking, world, assistant)
        body = return_body(*item_ids(rental), flaggedForDamage=True)
        answered(take_back(booking, assistant, rental["id"], body))
        again = answered(read_rental(booking, assistant, rental["id"]))
        item = only_item(again)
        assert (item["conditionIn"], item["damageAssessment"]) == ("A", "REQUIRED")
        assert again["settlementWaitingOn"] == "DAMAGE_ASSESSMENT"
        assert unit_status(session, item["assetTag"]) is AssetStatus.QUARANTINED


class TestFilingAReport:
    """The decision is recorded, the unit leaves availability and the deposit resumes."""

    def test_a_report_that_is_not_chargeable_releases_the_whole_deposit(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        back = returned_worse(booking, world, assistant)
        item = only_item(back)
        response = file_report(
            booking,
            assistant,
            report_body(item["assetTag"], chargeable=False, rental_item_id=item["id"]),
        )
        report = created(response)
        assert set(report) == REPORT_MEMBERS
        assert REFERENCE_PATTERN.match(str(report["reference"]))
        assert response.headers["Location"] == f"/api/damage-reports/{report['id']}"
        assert (report["status"], report["chargeableToCustomer"], report["recoveryCharged"]) == (
            "OPEN", False, None
        )
        assert (report["rentalId"], report["rentalReference"], report["rentalItemId"]) == (
            back["id"], back["reference"], item["id"]
        )
        assert (report["replacementValue"], report["repairEstimate"]) == ("4200.00", "450.00")
        assert (report["branchCode"], report["reportedByName"]) == (
            world.branch.code, "Wesley Adonis"
        )
        settled = answered(read_rental(booking, assistant, back["id"]))
        assert (settled["status"], settled["depositRefunded"]) == ("SETTLED", "1200.00")
        assert only_item(settled)["damageAssessment"] == "DONE"
        assert charges_of(settled, "DAMAGE_RECOVERY") == []

    def test_a_report_outside_a_hire_quarantines_the_unit_and_charges_nobody(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        tag = world.assets[0].asset_tag
        report = created(file_report(booking, assistant, report_body(tag, chargeable=True)))
        assert (report["rentalId"], report["rentalItemId"], report["recoveryCharged"]) == (
            None, None, None
        )
        assert (report["chargeableToCustomer"], report["replacementValue"]) == (True, "4200.00")
        assert unit_status(session, tag) is AssetStatus.QUARANTINED
        events = session.exec(select(AuditEvent)).all()
        actions = {event.action: event.after_state or {} for event in events}
        assert actions["damage_report.filed"]["reference"] == report["reference"]
        assert actions["asset.status_changed"]["status"] == "QUARANTINED"

    def test_a_second_report_on_a_unit_in_quarantine_leaves_it_there(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount, session: Session
    ) -> None:
        tag = world.assets[0].asset_tag
        created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        listed = answered(list_reports(booking, assistant, assetTag=tag.lower()))
        assert listed["total"] == TWO_REPORTS
        assert unit_status(session, tag) is AssetStatus.QUARANTINED


class TestReadingReports:
    """One by its key or its reference, and a list newest first that narrows."""

    def test_one_report_is_read_by_its_key_or_its_reference(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        tag = world.assets[0].asset_tag
        report = created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        by_key = answered(read_report(booking, assistant, report["id"]))
        by_reference = answered(read_report(booking, assistant, str(report["reference"]).lower()))
        assert by_key == by_reference == report

    def test_the_list_is_newest_first_and_narrowed_by_tag_status_and_branch(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        first, second = (unit.asset_tag for unit in world.assets)
        older = created(file_report(booking, assistant, report_body(first, chargeable=False)))
        booking.clock.advance(FIVE_MINUTES)
        newer = created(file_report(booking, assistant, report_body(second, chargeable=False)))
        answered(send_for_repair(booking, administrator, newer["id"]))

        everything = answered(list_reports(booking, assistant, branchCode=world.branch.code))
        assert [report["id"] for report in everything["items"]] == [newer["id"], older["id"]]
        assert (everything["page"], everything["pageSize"], everything["total"]) == (
            1, 20, TWO_REPORTS
        )
        open_only = answered(list_reports(booking, assistant, status="OPEN"))
        assert [report["id"] for report in open_only["items"]] == [older["id"]]
        by_tag = answered(list_reports(booking, assistant, assetTag=second, pageSize=1))
        assert [report["status"] for report in by_tag["items"]] == ["UNDER_REPAIR"]
        assert answered(list_reports(booking, assistant, assetTag="TSH-NO-0000"))["total"] == 0


class TestRepairAndClosing:
    """Repair moves the unit with the report, and the close decides where it ends up."""

    def test_repair_then_resolution_puts_the_unit_back_on_the_shelf(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        tag = world.assets[0].asset_tag
        report = created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        repaired = answered(send_for_repair(booking, administrator, report["reference"]))
        assert repaired["status"] == "UNDER_REPAIR"
        assert unit_status(session, tag) is AssetStatus.UNDER_REPAIR
        body = {"outcome": "RESOLVED", "actualRepairCost": "380", "resolutionNotes": " New gear "}
        resolved = answered(close_report(booking, administrator, report["id"], body))
        assert (resolved["status"], resolved["actualRepairCost"]) == ("RESOLVED", "380.00")
        assert (resolved["resolutionNotes"], resolved["resolvedAt"]) == (
            "New gear", "2026-03-02T10:00:00+02:00"
        )
        assert unit_status(session, tag) is AssetStatus.AVAILABLE

    def test_resolving_one_of_two_open_reports_keeps_the_unit_out(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        tag = world.assets[0].asset_tag
        first = created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        created(file_report(booking, assistant, report_body(tag, chargeable=False)))
        body = {"outcome": "RESOLVED", "actualRepairCost": "0.00"}
        answered(close_report(booking, administrator, first["id"], body))
        assert unit_status(session, tag) is AssetStatus.QUARANTINED

    def test_a_write_off_retires_the_unit_and_keeps_its_row_and_its_hire(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
        session: Session,
    ) -> None:
        back = returned_worse(booking, world, assistant)
        item = only_item(back)
        body = report_body(item["assetTag"], chargeable=False, rental_item_id=item["id"])
        report = created(file_report(booking, assistant, body))
        closed = answered(
            close_report(booking, administrator, report["id"], {"outcome": "WRITTEN_OFF"})
        )
        assert (closed["status"], closed["actualRepairCost"]) == ("WRITTEN_OFF", None)
        unit = session.exec(select(Asset).where(col(Asset.asset_tag) == item["assetTag"])).one()
        session.refresh(unit)
        assert (unit.status, str(unit.retired_on)) == (AssetStatus.RETIRED, "2026-03-02")
        hire = answered(read_rental(booking, assistant, back["id"]))
        assert only_item(hire)["assetTag"] == item["assetTag"]
        assert answered(read_report(booking, assistant, report["id"]))["status"] == "WRITTEN_OFF"
        assert UUID(str(closed["id"])) == UUID(str(report["id"]))
