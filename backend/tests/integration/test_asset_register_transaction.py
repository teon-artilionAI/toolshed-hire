"""Each write of the asset register as a real transaction on PostgreSQL (FR-23, BR-37, BR-49).

Every write commits with its audit event or not at all, so a write whose
audit event cannot be written leaves the register exactly as it was, and one
that commits leaves exactly one event about the unit.

Through the routes, a unit a booking holds is not retired and the booking is
named. A retired unit keeps its row, stays in the register, is never offered
by the availability search again and keeps its figures in the utilisation
report for the days it was in the fleet. A move by hand is a change of status
the report reads, so a unit quarantined by hand is out of service from the
day it was moved and not from the day it was acquired. The race for a tag is
in tests/integration/test_asset_register_race.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session, col, select

from app.application.catalogue.admin_commands import Change
from app.application.catalogue.asset_commands import (
    EditUnitCommand,
    MoveUnitCommand,
    RegisterUnitCommand,
    UnitChanges,
)
from app.application.catalogue.move_asset import MoveUnitUseCase
from app.application.catalogue.register_asset import EditUnitUseCase, RegisterUnitUseCase
from app.domain.enums import AssetStatus, UserRole
from app.domain.identity import Actor
from app.infrastructure.asset_register_query import SqlAssetRegister
from app.infrastructure.models import (
    Asset,
    AuditEvent,
    Reservation,
    ReservationLine,
    UserAccount,
)
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.admin_asset_api import REASON, list_assets, move_asset, read_asset
from tests.support.booking import AuditWriteFailed, UnitOfWorkWithBrokenAudit, opening
from tests.support.booking_api import BookingClient, answered
from tests.support.catalogue import hold_unit
from tests.support.checkout_api import TODAY_HIRE
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.factories import Factory
from tests.support.register_pg import SHELF_TAG as TAG
from tests.support.register_pg import Shelf, new_terms, stock_shelf
from tests.support.register_pg import admin_actor as actor_of
from tests.support.report_api import read_report

pytestmark = pytest.mark.postgres

type Write = Callable[[SqlAlchemyUnitOfWork, SqlAssetRegister], object]


@pytest.fixture
def reader(postgres_engine: Engine, postgres_session: Session) -> Iterator[Session]:
    """Yield a session of its own, closed before the tables are emptied again."""
    with Session(postgres_engine) as session:
        yield session


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


@pytest.fixture
def shelf(postgres_session: Session, postgres_factory: Factory) -> Shelf:
    """Commit a branch, a published hammer and one unit of it on the shelf."""
    return stock_shelf(postgres_session, postgres_factory)


def writes(actor: Actor, model_id: UUID) -> dict[str, Write]:
    """Return each write of the register, bound to the stored model and unit."""
    clock = FixedClock()
    return {
        "register a unit": lambda uow, read: RegisterUnitUseCase(uow, clock, read).execute(
            RegisterUnitCommand(
                actor=actor, model_id=model_id, branch_code="CBD", terms=new_terms()
            )
        ),
        "edit a unit": lambda uow, read: EditUnitUseCase(uow, clock, read).execute(
            EditUnitCommand(
                actor=actor, asset_tag=TAG, changes=UnitChanges(notes=Change("Chuck replaced."))
            )
        ),
        "move a unit": lambda uow, read: MoveUnitUseCase(uow, clock, read).execute(
            MoveUnitCommand(
                actor=actor, asset_tag=TAG, target=AssetStatus.QUARANTINED, reason=REASON
            )
        ),
    }


WRITES: Final[list[str]] = ["register a unit", "edit a unit", "move a unit"]


def register_as_stored(session: Session) -> tuple[object, ...]:
    """Return every unit and the number of audit events, read afresh."""
    session.expire_all()
    units = sorted(
        (row.asset_tag, row.status.value, row.notes) for row in session.exec(select(Asset)).all()
    )
    events = session.execute(text("SELECT count(*) FROM audit_event")).scalar_one()
    return tuple(units), events


class TestEachWriteIsOneTransaction:
    """A write commits with its event or not at all."""

    @pytest.mark.parametrize("name", WRITES)
    def test_a_write_whose_audit_event_fails_keeps_nothing(
        self,
        postgres_engine: Engine,
        reader: Session,
        administrator: UserAccount,
        shelf: Shelf,
        name: str,
    ) -> None:
        with Session(postgres_engine) as check:
            before = register_as_stored(check)
            write = writes(actor_of(administrator), shelf.model.id)[name]
            with pytest.raises(AuditWriteFailed):
                write(
                    opening(postgres_engine, UnitOfWorkWithBrokenAudit)(), SqlAssetRegister(reader)
                )
            assert register_as_stored(check) == before

    @pytest.mark.parametrize("name", WRITES)
    def test_a_write_that_commits_leaves_one_event_about_the_unit(
        self,
        postgres_engine: Engine,
        reader: Session,
        administrator: UserAccount,
        shelf: Shelf,
        name: str,
    ) -> None:
        write = writes(actor_of(administrator), shelf.model.id)[name]
        write(opening(postgres_engine)(), SqlAssetRegister(reader))
        with Session(postgres_engine) as check:
            events = check.exec(select(AuditEvent)).all()
            assert len(events) == 1
            assert (events[0].entity_type, events[0].occurred_at) == ("asset", DEFAULT_INSTANT)


class TestARetiredUnitThroughTheRoutes:
    """A retired unit stays readable, is never offered again and keeps its figures."""

    def test_a_unit_a_booking_holds_is_not_retired_and_the_booking_is_named(
        self,
        booking: BookingClient,
        postgres_session: Session,
        postgres_factory: Factory,
        administrator: UserAccount,
        shelf: Shelf,
    ) -> None:
        allocation = hold_unit(postgres_factory, shelf.unit, TODAY_HIRE)
        postgres_session.commit()
        line = postgres_session.get(ReservationLine, allocation.reservation_line_id)
        assert line is not None
        held_for = postgres_session.get(Reservation, line.reservation_id)
        assert held_for is not None
        response = move_asset(booking, administrator, TAG, "RETIRED")
        assert response.status_code == 409, response.text
        assert held_for.reference in response.json()["detail"]
        unit = answered(read_asset(booking, administrator, TAG))
        assert (unit["status"], unit["activeAllocationCount"]) == ("AVAILABLE", 1)

    def test_a_retired_unit_is_never_offered_and_keeps_its_figures(
        self,
        booking: BookingClient,
        postgres_session: Session,
        administrator: UserAccount,
        shelf: Shelf,
    ) -> None:
        answered(move_asset(booking, administrator, TAG, "RETIRED"))
        offered = answered(
            booking.client.get(
                f"/api/catalogue/models/{shelf.model.slug}/availability",
                params={"from": "2026-03-09", "to": "2026-03-12", "quantity": 1},
            )
        )
        assert [branch["available"] for branch in offered["branches"]] == [False]
        listed = answered(list_assets(booking, administrator, status="RETIRED"))
        assert [item["assetTag"] for item in listed["items"]] == [TAG]
        stored = postgres_session.exec(select(Asset).where(col(Asset.asset_tag) == TAG)).one()
        postgres_session.refresh(stored)
        assert (stored.status, stored.retired_on) == (AssetStatus.RETIRED, date(2026, 3, 2))
        february = _line_of(booking, administrator, "2026-02-01", "2026-03-01")
        assert (february["serviceableDays"], february["status"]) == (28, "RETIRED")
        across = _line_of(booking, administrator, "2026-03-01", "2026-03-04")
        assert across["serviceableDays"] == 1

    def test_a_unit_quarantined_by_hand_is_out_of_service_from_the_day_it_moved(
        self, booking: BookingClient, administrator: UserAccount, shelf: Shelf
    ) -> None:
        answered(move_asset(booking, administrator, TAG, "QUARANTINED"))
        line = _line_of(booking, administrator, "2026-03-01", "2026-03-04")
        assert (line["serviceableDays"], line["status"]) == (1, "QUARANTINED")


def _line_of(
    booking: BookingClient, administrator: UserAccount, first: str, after: str
) -> dict[str, object]:
    """Return the report's line for the unit over a period."""
    period = {"from": first, "to": after}
    report = answered(read_report(booking, administrator, groupBy="asset", **period))
    items = report["items"]
    assert isinstance(items, list)
    (line,) = [item for item in items if item["assetTag"] == TAG]
    return dict(line)


def _line_of(
    booking: BookingClient, administrator: UserAccount, first: str, after: str
) -> dict[str, object]:
    """Return the report's line for the unit over a period."""
    period = {"from": first, "to": after}
    report = answered(read_report(booking, administrator, groupBy="asset", **period))
    items = report["items"]
    assert isinstance(items, list)
    (line,) = [item for item in items if item["assetTag"] == TAG]
    return dict(line)
