"""Moving a unit by hand and reading the history of a hire, through HTTP (US-31, US-32, BR-38).

A new unit goes from INTAKE to the shelf and the move is in its history. A
retired unit keeps its row and stays in the register with its history. That
it is never offered for hire again is shown on PostgreSQL in
tests/integration/test_asset_register_transaction.py, because the
availability search needs a range type. The history of a unit that went out
on hire reads its booking, its hire and its moves. These run against the in
memory database on the still clock of the booking tests.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import Asset, UserAccount
from tests.support.admin_asset_api import (
    NEW_TAG,
    REASON,
    asset_body,
    create_asset,
    list_assets,
    move_asset,
    read_asset,
)
from tests.support.admin_asset_fleet import (
    HAMMER_TAG,
    Fleet,
    history_in,
    stock_fleet,
    tags_of,
)
from tests.support.booking_api import BookingClient, answered, build_booking_world, created
from tests.support.checkout_api import checked_out, confirmed_today
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


class TestMovingByHand:
    """A unit moves through its lifecycle, and a retired one stays readable."""

    def test_a_new_unit_goes_on_the_shelf_and_the_move_is_in_its_history(
        self, booking: BookingClient, administrator: UserAccount, fleet: Fleet
    ) -> None:
        created(create_asset(booking, administrator, asset_body(fleet.hammer.id, "CBD")))
        unit = answered(move_asset(booking, administrator, NEW_TAG, "AVAILABLE", None))
        assert (unit["status"], unit["allowedTransitions"]) == (
            "AVAILABLE",
            ["QUARANTINED", "UNDER_REPAIR", "RETIRED"],
        )
        assert [entry["summary"] for entry in history_in(unit)] == [
            "Moved from INTAKE to AVAILABLE.",
            "Registered in the fleet at INTAKE.",
        ]

    def test_a_retired_unit_keeps_its_row_and_stays_in_the_register(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        fleet: Fleet,
    ) -> None:
        unit = answered(move_asset(booking, administrator, HAMMER_TAG, "RETIRED"))
        assert (unit["status"], unit["retiredOn"], unit["allowedTransitions"]) == (
            "RETIRED",
            "2026-03-02",
            [],
        )
        assert history_in(unit)[0]["summary"] == f"Moved from AVAILABLE to RETIRED. {REASON}"
        assert tags_of(answered(list_assets(booking, administrator, status="RETIRED"))) == [
            HAMMER_TAG
        ]
        assert answered(read_asset(booking, administrator, HAMMER_TAG))["status"] == "RETIRED"
        stored = session.exec(select(Asset).where(col(Asset.asset_tag) == HAMMER_TAG)).one()
        session.refresh(stored)
        assert (stored.status, str(stored.retired_on)) == (AssetStatus.RETIRED, "2026-03-02")


class TestTheHistoryOfAHire:
    """The history of a unit that went out reads its booking, its hire and its moves."""

    def test_a_unit_checked_out_shows_its_booking_its_hire_and_its_move(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        staff = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        reservation = confirmed_today(booking, world, staff)
        rental = checked_out(booking, staff, reservation["id"])
        unit = answered(read_asset(booking, administrator, world.assets[0].asset_tag))
        assert (unit["status"], unit["activeAllocationCount"]) == ("ON_HIRE", 1)
        assert unit["allowedTransitions"] == []
        entries = {(entry["kind"], entry["reference"]) for entry in history_in(unit)}
        assert entries == {
            ("ALLOCATION", reservation["reference"]),
            ("RENTAL", rental["reference"]),
            ("AUDIT_EVENT", rental["reference"]),
        }
        summaries = [entry["summary"] for entry in history_in(unit)]
        assert "Moved from AVAILABLE to ON_HIRE." in summaries
        assert any(str(summary).startswith("Handed over on hire") for summary in summaries)
