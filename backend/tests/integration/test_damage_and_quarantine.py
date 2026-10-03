"""Damage and quarantine on PostgreSQL itself (BR-10, BR-35, BR-37 to BR-39, BR-49).

A unit that comes back damaged leaves the availability search at once, and the
resolution of its report brings it back, which only the real statement of the
search can prove. A report, its recovery charge and the settlement it lets go
are one transaction, so an audit event that cannot be written leaves none of
them behind. A write off retires the unit and keeps its row, its hire and its
report readable, and the database's own check on the retirement date agrees.

The hire goes out on Monday the second of March 2026, comes back the same day
a grade worse, and the search asks about the tenth to the twelfth.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session, col, select

from app.application.hire.file_damage_report import (
    FileDamageReportCommand,
    FileDamageReportUseCase,
)
from app.domain.damage_filing import DamageFiling
from app.domain.enums import AssetStatus, ChargeType, DamageSeverity, RentalStatus, UserRole
from app.domain.identity import Actor
from app.domain.money import Money
from app.infrastructure.models import Asset, AuditEvent, Charge, DamageReport, Rental, UserAccount
from app.infrastructure.schema_ddl import DAMAGE_REPORT_ASSET_INDEX, DAMAGE_REPORT_RENTAL_ITEM_INDEX
from tests.support.booking import AuditWriteFailed, UnitOfWorkWithBrokenAudit, opening
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.catalogue import model_availability_path
from tests.support.checkout_api import read_rental
from tests.support.clock import FixedClock
from tests.support.damage_api import (
    close_report,
    file_report,
    only_item,
    read_report,
    report_body,
    returned_worse,
)
from tests.support.factories import Factory
from tests.support.rental_api import worked_example_world

pytestmark = pytest.mark.postgres

AFTER_THE_HIRE: Final[dict[str, str]] = {"from": "2026-03-10", "to": "2026-03-12"}
RESOLVED: Final[dict[str, str]] = {"outcome": "RESOLVED", "actualRepairCost": "380.00"}
EXPLAIN_PREFIX: Final[str] = "EXPLAIN "


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed world of one unit with the deposit of the worked example."""
    return worked_example_world(postgres_session, postgres_factory)


@pytest.fixture
def assistant(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return account


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


def free_at_the_branch(booking: BookingClient, world: BookingWorld) -> bool:
    """Return whether the search offers the world's model at its branch after the hire."""
    response = booking.client.get(
        model_availability_path(world.product_model.slug), params=AFTER_THE_HIRE
    )
    answers = {answer["branchCode"]: answer["available"] for answer in response.json()["branches"]}
    return bool(answers[world.branch.code])


def chargeable_report(
    engine: Engine, staff: Actor, asset_tag: str, item_id: UUID, broken_audit: bool
) -> None:
    """File a report that charges R450.00, on a connection of its own."""
    build = opening(engine, UnitOfWorkWithBrokenAudit) if broken_audit else opening(engine)
    FileDamageReportUseCase(build(), FixedClock()).execute(
        FileDamageReportCommand(
            actor=staff,
            asset_tag=asset_tag,
            filing=DamageFiling(
                rental_item_id=item_id,
                severity=DamageSeverity.MAJOR,
                description="Bent chuck",
                repair_estimate=Money.create("600.00"),
                chargeable_to_customer=True,
                recovery_amount=Money.create("450.00"),
            ),
        )
    )


def stored(engine: Engine, rental_id: UUID) -> dict[str, object]:
    """Return what is committed of a hire and its reports, read on a connection of its own."""
    with Session(engine) as reader:
        rental = reader.get(Rental, rental_id)
        assert rental is not None
        reports = reader.exec(select(DamageReport)).all()
        recoveries = reader.exec(
            select(Charge).where(col(Charge.charge_type) == ChargeType.DAMAGE_RECOVERY)
        ).all()
        return {
            "status": rental.status,
            "withheld": rental.deposit_withheld,
            "reports": [report.reference for report in reports],
            "recovery_points_at": [charge.damage_report_id for charge in recoveries],
            "report_ids": [report.id for report in reports],
        }


class TestQuarantineAndTheSearch:
    """The search never offers a quarantined unit, and offers it again once resolved (BR-10)."""

    def test_a_damaged_return_leaves_the_unit_out_of_the_search(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        assert free_at_the_branch(booking, world) is True
        returned_worse(booking, world, assistant)
        assert free_at_the_branch(booking, world) is False

    def test_the_resolution_of_its_report_returns_the_unit_to_the_search(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        item = only_item(returned_worse(booking, world, assistant))
        body = report_body(item["assetTag"], chargeable=False, rental_item_id=item["id"])
        report = created(file_report(booking, assistant, body))
        assert free_at_the_branch(booking, world) is False
        answered(close_report(booking, administrator, report["id"], RESOLVED))
        assert free_at_the_branch(booking, world) is True


class TestAReportIsOneTransaction:
    """The report, its recovery and the settlement are kept together or not at all."""

    def test_an_audit_event_that_cannot_be_written_undoes_all_of_it(
        self,
        postgres_engine: Engine,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        back = returned_worse(booking, world, assistant)
        item = only_item(back)
        rental_id, item_id = UUID(str(back["id"])), UUID(str(item["id"]))
        staff = Actor(user_id=assistant.id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id)
        with pytest.raises(AuditWriteFailed):
            chargeable_report(postgres_engine, staff, str(item["assetTag"]), item_id, True)
        assert stored(postgres_engine, rental_id) == {
            "status": RentalStatus.RETURNED,
            "withheld": Decimal("0.00"),
            "reports": [],
            "recovery_points_at": [],
            "report_ids": [],
        }

        chargeable_report(postgres_engine, staff, str(item["assetTag"]), item_id, False)
        kept = stored(postgres_engine, rental_id)
        assert (kept["status"], kept["withheld"]) == (RentalStatus.SETTLED, Decimal("450.00"))
        assert kept["recovery_points_at"] == kept["report_ids"] and len(kept["report_ids"]) == 1


class TestAWriteOff:
    """The unit is retired and its row, its hire and its report stay readable (BR-38)."""

    def test_a_write_off_keeps_the_row_and_its_history(
        self,
        postgres_engine: Engine,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        administrator: UserAccount,
    ) -> None:
        back = returned_worse(booking, world, assistant)
        item = only_item(back)
        body = report_body(item["assetTag"], chargeable=False, rental_item_id=item["id"])
        report = created(file_report(booking, assistant, body))
        answered(close_report(booking, administrator, report["id"], {"outcome": "WRITTEN_OFF"}))

        with Session(postgres_engine) as reader:
            unit = reader.exec(select(Asset).where(col(Asset.asset_tag) == item["assetTag"])).one()
            assert (unit.status, str(unit.retired_on)) == (AssetStatus.RETIRED, "2026-03-02")
            moves = [
                (event.after_state or {}).get("status")
                for event in reader.exec(
                    select(AuditEvent)
                    .where(col(AuditEvent.entity_id) == unit.id)
                    .order_by(col(AuditEvent.id))
                )
            ]
        assert moves == ["ON_HIRE", "QUARANTINED", "RETIRED"]
        hire = answered(read_rental(booking, assistant, back["id"]))
        assert (only_item(hire)["conditionIn"], hire["status"]) == ("B", "SETTLED")
        assert answered(read_report(booking, assistant, report["id"]))["status"] == "WRITTEN_OFF"


class TestTheIndexes:
    """Each read of the reports stands on the index of revision 0005 written for it."""

    @pytest.mark.parametrize(
        ("statement", "index"),
        [
            (
                "SELECT 1 FROM damage_report WHERE rental_item_id = :key",
                DAMAGE_REPORT_RENTAL_ITEM_INDEX,
            ),
            ("SELECT id FROM damage_report WHERE asset_id = :key", DAMAGE_REPORT_ASSET_INDEX),
        ],
    )
    def test_the_planner_can_use_the_index(
        self, postgres_session: Session, statement: str, index: str
    ) -> None:
        postgres_session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = postgres_session.execute(
            text(EXPLAIN_PREFIX + statement), {"key": UUID(int=1)}
        ).all()
        assert index in "\n".join(str(row[0]) for row in plan)
