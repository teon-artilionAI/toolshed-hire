"""The asset register's list, a registration and an edit, through HTTP (FR-23, US-31, BR-34).

The administrator lists every unit, retired or not, in tag order, narrows the
list by branch, status and model and searches it by part of the tag, the
serial number or the model name. A unit is registered at INTAKE and answers
201 with its history, and its paperwork is edited. These run against the in
memory database on the still clock of the booking tests. The moves by hand
and the history of a hire are in tests/api/test_admin_asset_moves.py, and the
refusals in tests/api/test_admin_asset_refusals.py.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import Asset, AuditEvent, UserAccount
from tests.support.admin_api import PAGE_MEMBERS
from tests.support.admin_asset_api import (
    ASSET_MEMBERS,
    DETAIL_MEMBERS,
    HISTORY_MEMBERS,
    NEW_TAG,
    asset_body,
    create_asset,
    edit_asset,
    list_assets,
    read_asset,
)
from tests.support.admin_asset_fleet import (
    BREAKER_TAG,
    HAMMER_TAG,
    QUARANTINED_TAG,
    Fleet,
    history_in,
    stock_fleet,
    tags_of,
)
from tests.support.booking_api import BookingClient, answered, created
from tests.support.catalogue import hold_unit
from tests.support.checkout_api import TODAY_HIRE
from tests.support.damage_api import file_report, report_body
from tests.support.factories import Factory


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def fleet(session: Session, factory: Factory) -> Fleet:
    """Commit the small fleet of `tests/support/admin_asset_fleet.py`."""
    return stock_fleet(session, factory)


class TestTheList:
    """Every unit, retired or not, in tag order, narrowed and searched as asked."""

    def test_every_unit_is_listed_in_tag_order_in_the_shape_of_the_contract(
        self, booking: BookingClient, administrator: UserAccount, fleet: Fleet
    ) -> None:
        page = answered(list_assets(booking, administrator))
        assert set(page) == PAGE_MEMBERS
        assert (tags_of(page), page["total"], page["pageSize"]) == (
            [BREAKER_TAG, HAMMER_TAG, QUARANTINED_TAG],
            3,
            20,
        )
        items = page["items"]
        assert isinstance(items, list)
        hammer = items[1]
        assert set(hammer) == ASSET_MEMBERS
        assert (hammer["modelName"], hammer["categoryName"], hammer["branchCode"]) == (
            "Rotary hammer",
            "Drilling",
            "CBD",
        )
        assert (hammer["status"], hammer["acquisitionCost"], hammer["retiredOn"]) == (
            "AVAILABLE",
            "3980.00",
            None,
        )
        assert hammer["allowedTransitions"] == ["QUARANTINED", "UNDER_REPAIR", "RETIRED"]
        assert items[2]["allowedTransitions"] == ["AVAILABLE", "UNDER_REPAIR", "RETIRED"]

    def test_the_list_is_narrowed_by_branch_status_and_model(
        self, booking: BookingClient, administrator: UserAccount, fleet: Fleet
    ) -> None:
        def listed(**params: object) -> list[object]:
            return tags_of(answered(list_assets(booking, administrator, **params)))

        assert listed(branchCode="BLV") == [QUARANTINED_TAG]
        assert listed(branchCode="cbd", status="AVAILABLE") == [BREAKER_TAG, HAMMER_TAG]
        assert listed(status="QUARANTINED") == [QUARANTINED_TAG]
        assert listed(modelId=str(fleet.hammer.id)) == [HAMMER_TAG, QUARANTINED_TAG]

    @pytest.mark.parametrize(
        ("text", "found"),
        [
            ("dr-004", [HAMMER_TAG, QUARANTINED_TAG]),
            ("77120", [BREAKER_TAG]),
            ("demolition", [BREAKER_TAG]),
            ("hammer", [HAMMER_TAG, QUARANTINED_TAG]),
            ("%%", []),
        ],
    )
    def test_the_search_matches_part_of_the_tag_the_serial_or_the_model_name(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        fleet: Fleet,
        text: str,
        found: list[str],
    ) -> None:
        assert tags_of(answered(list_assets(booking, administrator, q=text))) == found

    def test_a_page_is_cut_from_the_list(
        self, booking: BookingClient, administrator: UserAccount, fleet: Fleet
    ) -> None:
        page = answered(list_assets(booking, administrator, page=2, pageSize=2))
        assert (tags_of(page), page["total"], page["page"]) == ([QUARANTINED_TAG], 3, 2)

    def test_a_unit_carries_the_bookings_that_hold_it_and_its_open_reports(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        fleet: Fleet,
    ) -> None:
        hammer = session.exec(select(Asset).where(col(Asset.asset_tag) == HAMMER_TAG)).one()
        hold_unit(factory, hammer, TODAY_HIRE)
        session.commit()
        created(file_report(booking, administrator, report_body(BREAKER_TAG, chargeable=False)))
        page = answered(list_assets(booking, administrator, branchCode="CBD"))
        items = page["items"]
        assert isinstance(items, list)
        counts = {
            item["assetTag"]: (item["activeAllocationCount"], item["openDamageReports"])
            for item in items
        }
        assert counts == {HAMMER_TAG: (1, 0), BREAKER_TAG: (0, 1)}


class TestRegisteringAndEditing:
    """A unit is registered at INTAKE, and its paperwork changes with an event."""

    def test_a_unit_is_registered_at_intake_and_answered_with_its_history(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        fleet: Fleet,
    ) -> None:
        body = asset_body(fleet.breaker.id, "CBD", notes="  Two chisels in the case. ")
        unit = created(create_asset(booking, administrator, body))
        assert set(unit) == DETAIL_MEMBERS
        assert (unit["assetTag"], unit["status"], unit["branchName"]) == (
            NEW_TAG,
            "INTAKE",
            "Cape Town CBD",
        )
        assert (unit["notes"], unit["acquiredOn"], unit["acquisitionCost"]) == (
            "Two chisels in the case.",
            "2026-02-01",
            "3900.00",
        )
        assert unit["allowedTransitions"] == ["AVAILABLE", "QUARANTINED"]
        (entry,) = history_in(unit)
        assert set(entry) == HISTORY_MEMBERS
        assert (entry["kind"], entry["summary"], entry["at"]) == (
            "AUDIT_EVENT",
            "Registered in the fleet at INTAKE.",
            "2026-03-02T10:00:00+02:00",
        )
        actions = session.exec(
            select(AuditEvent.action).where(col(AuditEvent.entity_id) == UUID(str(unit["id"])))
        ).all()
        assert list(actions) == ["asset.registered"]

    def test_an_edit_changes_the_paperwork_it_names_and_keeps_the_rest(
        self, booking: BookingClient, administrator: UserAccount, fleet: Fleet
    ) -> None:
        unit = answered(
            edit_asset(
                booking,
                administrator,
                BREAKER_TAG,
                {"serialNumber": None, "conditionGrade": "B", "hourMeterReading": 412},
            )
        )
        assert (unit["serialNumber"], unit["conditionGrade"], unit["hourMeterReading"]) == (
            None,
            "B",
            412,
        )
        assert (unit["assetTag"], unit["branchCode"], unit["status"]) == (
            BREAKER_TAG,
            "CBD",
            "AVAILABLE",
        )
        assert history_in(unit)[0]["summary"] == (
            "Changed the serial number, the grade and the meter reading."
        )

    def test_a_tag_in_the_path_is_read_in_capitals(
        self, booking: BookingClient, administrator: UserAccount, fleet: Fleet
    ) -> None:
        assert answered(read_asset(booking, administrator, "tsh-dr-0042"))["assetTag"] == (
            HAMMER_TAG
        )
