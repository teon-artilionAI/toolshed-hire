"""Every refusal of a move by hand through the asset register, through HTTP (US-31, BR-37).

A move to ON_HIRE or LOST is a 422 naming `to`, and so is a status nobody
knows. A move out of service without a reason, or with one out of bounds, is
a 422 naming `reason`. A move the lifecycle does not permit is a 409 naming
the status the unit is in, a retired unit moves nowhere, a unit on hire comes
off hire through its return, a retirement while a booking holds the unit is a
409 naming the booking, and a unit with a damage report open is not put back
on the shelf by hand. A refused move leaves the unit where it was and writes
no event. These run against the in memory database.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import Asset, Branch, ProductModel, UserAccount
from tests.support.admin_asset_api import (
    booking_holding,
    move_asset,
    refused_with,
    stored_events,
)
from tests.support.booking_api import BookingClient, created
from tests.support.catalogue import a_category, a_model, hold_unit
from tests.support.checkout_api import TODAY_HIRE
from tests.support.damage_api import file_report, report_body
from tests.support.factories import Factory
from tests.support.report_api import refused_fields

TAG: Final[str] = "TSH-DR-0042"
UNKNOWN_TAG: Final[str] = "TSH-ZZ-0000"
TRANSITION: Final[str] = "state-transition"


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def branch(session: Session, factory: Factory) -> Branch:
    """Return the committed CBD branch."""
    row = factory.branch(code="CBD")
    session.commit()
    return row


@pytest.fixture
def model(session: Session, factory: Factory) -> ProductModel:
    """Return a committed model in an active category."""
    row = a_model(factory, name="Rotary hammer", category=a_category(factory, name="Drilling"))
    session.commit()
    return row


@pytest.fixture
def unit(session: Session, factory: Factory, branch: Branch, model: ProductModel) -> Asset:
    """Return a committed unit on the shelf at CBD."""
    row = factory.asset(product_model=model, branch=branch, asset_tag=TAG)
    session.commit()
    return row


class TestMovingRefusesWhatTheLifecycleForbids:
    """A move is refused by field, by the lifecycle, or by what still holds the unit."""

    @pytest.mark.parametrize(
        ("to", "reason", "field"),
        [
            ("ON_HIRE", "Handed over by hand.", "body.to"),
            ("LOST", "Nobody can find it.", "body.to"),
            ("BROKEN", "Broken.", "body.to"),
            ("QUARANTINED", None, "body.reason"),
            ("UNDER_REPAIR", "   ", "body.reason"),
            ("RETIRED", "old", "body.reason"),
            ("RETIRED", "R" * 201, "body.reason"),
        ],
    )
    def test_a_refused_field_is_named_and_the_unit_stays_where_it_was(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        unit: Asset,
        to: str,
        reason: str | None,
        field: str,
    ) -> None:
        response = move_asset(booking, administrator, TAG, to, reason)
        assert refused_fields(response) == {field}
        session.refresh(unit)
        assert (unit.status, stored_events(session)) == (AssetStatus.AVAILABLE, [])

    def test_a_move_the_lifecycle_does_not_permit_is_a_409_naming_the_status(
        self, booking: BookingClient, administrator: UserAccount, unit: Asset
    ) -> None:
        problem = refused_with(
            move_asset(booking, administrator, TAG, "INTAKE", None), status.HTTP_409_CONFLICT
        )
        assert problem["type"] == f"https://toolshedhire.co.za/problems/{TRANSITION}"
        assert "on the shelf" in str(problem["detail"])
        assert problem["errors"] == {"from_status": "AVAILABLE", "to_status": "INTAKE"}

    def test_a_retired_unit_moves_nowhere(
        self, booking: BookingClient, administrator: UserAccount, unit: Asset
    ) -> None:
        retired = move_asset(booking, administrator, TAG, "RETIRED")
        assert retired.status_code == status.HTTP_200_OK
        problem = refused_with(
            move_asset(booking, administrator, TAG, "AVAILABLE", None), status.HTTP_409_CONFLICT
        )
        assert "retired" in str(problem["detail"])

    def test_a_unit_a_booking_holds_is_not_retired_and_the_booking_is_named(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        unit: Asset,
    ) -> None:
        allocation = hold_unit(factory, unit, TODAY_HIRE)
        session.commit()
        problem = refused_with(
            move_asset(booking, administrator, TAG, "RETIRED"), status.HTTP_409_CONFLICT
        )
        held_for = booking_holding(session, allocation.reservation_line_id)
        assert held_for in str(problem["detail"])
        session.refresh(unit)
        assert (unit.status, unit.retired_on) == (AssetStatus.AVAILABLE, None)

    def test_a_unit_with_a_damage_report_open_is_not_put_back_by_hand(
        self, booking: BookingClient, session: Session, administrator: UserAccount, unit: Asset
    ) -> None:
        report = created(file_report(booking, administrator, report_body(TAG, chargeable=False)))
        problem = refused_with(
            move_asset(booking, administrator, TAG, "AVAILABLE", None), status.HTTP_409_CONFLICT
        )
        assert str(report["reference"]) in str(problem["detail"])
        session.refresh(unit)
        assert unit.status is AssetStatus.QUARANTINED

    def test_a_unit_on_hire_is_moved_off_hire_by_its_return_only(
        self, booking: BookingClient, session: Session, administrator: UserAccount, unit: Asset
    ) -> None:
        unit.status = AssetStatus.ON_HIRE
        session.add(unit)
        session.commit()
        problem = refused_with(
            move_asset(booking, administrator, TAG, "AVAILABLE", None), status.HTTP_409_CONFLICT
        )
        assert "return" in str(problem["detail"])

    def test_a_tag_nobody_carries_is_not_found(
        self, booking: BookingClient, administrator: UserAccount, unit: Asset
    ) -> None:
        response = move_asset(booking, administrator, UNKNOWN_TAG, "QUARANTINED")
        assert response.status_code == status.HTTP_404_NOT_FOUND
