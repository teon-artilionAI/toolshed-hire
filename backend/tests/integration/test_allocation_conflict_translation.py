"""A real exclusion violation, raised by PostgreSQL, becomes a booking conflict.

The concurrency tests show that one of two racing bookings loses. They cannot
say which refusal the loser met, because the loser is usually turned away by
the pre check and never reaches the insert. These tests remove the pre check
from the picture, so the insert is the only thing that can refuse, and the
violation they provoke is the genuine SQLSTATE `23P01` from the genuine
constraint.

`SqlAssetRepository.translate_integrity_error` turns that one violation into
`AllocationConflictError`, which the API answers with 409. The second half of
the file proves the other direction, which matters as much. An integrity error
that is not the overlap constraint is not a booking conflict and is not
swallowed. Reporting a foreign key fault as "somebody else booked first" would
hide a real defect behind a polite message.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.application.availability.allocation import AllocationCommand, allocate_assets
from app.domain import catalogue
from app.domain.availability import AssetAllocation
from app.domain.enums import ReleaseReason
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod
from app.infrastructure.availability import SqlAssetRepository
from app.infrastructure.schema_ddl import (
    OVERLAP_CONSTRAINT_NAME,
    RELEASE_STATE_CONSTRAINT_NAME,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.pg import (
    CHECK_VIOLATION_SQLSTATE,
    EXCLUSION_VIOLATION_SQLSTATE,
    constraint_name_of,
    count_active_allocations,
    sqlstate_of,
)
from tests.support.scenarios import AllocationScenario, build_allocation_scenario

pytestmark = pytest.mark.postgres

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
OVERLAPPING_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 11), date(2026, 3, 15))
ALLOCATED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
FOREIGN_KEY_VIOLATION_SQLSTATE: Final[str] = "23503"


class StaleReadAssetRepository(SqlAssetRepository):
    """The real repository, except that its pre check is out of date.

    It reports a unit as free without looking, which is exactly what a
    transaction sees when it read the allocations a moment before another
    booking committed. The insert is the real one.
    """

    def __init__(self, session: Session, stale: list[catalogue.Asset]) -> None:
        """Keep the units the stale read will claim are free."""
        super().__init__(session)
        self._stale = stale

    def lock_allocatable(
        self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
    ) -> list[catalogue.Asset]:
        """Return the stale answer in place of the locking query."""
        return self._stale[:wanted]


@pytest.fixture
def booked(postgres_session: Session, postgres_factory: Factory) -> AllocationScenario:
    """Return a scenario whose only unit is already held for the first hire."""
    scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
    postgres_session.add(
        postgres_factory.allocation(line=scenario.line, asset=scenario.asset, period=FIRST_HIRE)
    )
    postgres_session.commit()
    return scenario


def an_allocation_of(scenario: AllocationScenario, period: BookingPeriod) -> AssetAllocation:
    """Return a domain allocation of the scenario's unit, not yet stored."""
    return AssetAllocation(
        reservation_line_id=scenario.line.id,
        asset_id=scenario.asset.id,
        branch_id=scenario.branch.id,
        period=period,
        allocated_at=ALLOCATED_AT,
    )


class TestTheOverlapConstraintBecomesAnAllocationConflict:
    """SQLSTATE 23P01 from `asset_allocation_no_overlap`, and only that."""

    def test_the_repository_raises_the_conflict_for_a_real_exclusion_violation(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        repository = SqlAssetRepository(postgres_session)
        with pytest.raises(AllocationConflictError) as refused:
            repository.save_allocations([an_allocation_of(booked, OVERLAPPING_HIRE)])
        postgres_session.rollback()

        assert refused.value.detail["constraint_name"] == OVERLAP_CONSTRAINT_NAME
        assert refused.value.code == "asset-unavailable"

    def test_the_conflict_keeps_the_database_error_as_its_cause(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        """The driver's own diagnostics, read here without the application's reader."""
        repository = SqlAssetRepository(postgres_session)
        with pytest.raises(AllocationConflictError) as refused:
            repository.save_allocations([an_allocation_of(booked, OVERLAPPING_HIRE)])
        postgres_session.rollback()

        cause = refused.value.__cause__
        assert isinstance(cause, IntegrityError)
        assert sqlstate_of(cause) == EXCLUSION_VIOLATION_SQLSTATE
        assert constraint_name_of(cause) == OVERLAP_CONSTRAINT_NAME

    def test_the_allocation_path_reports_what_was_being_asked_for(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        """The pre check is stale, so the constraint is what refuses the booking."""
        stale_unit = catalogue.Asset(
            id=booked.asset.id,
            asset_tag=booked.asset.asset_tag,
            product_model_id=booked.product_model.id,
            branch_id=booked.branch.id,
            status=booked.asset.status,
            condition_grade=booked.asset.condition_grade,
        )
        repository = StaleReadAssetRepository(postgres_session, [stale_unit])
        command = AllocationCommand(
            reservation_line_id=booked.line.id,
            product_model_id=booked.product_model.id,
            branch_id=booked.branch.id,
            period=OVERLAPPING_HIRE,
            quantity=1,
        )
        with pytest.raises(AllocationConflictError) as refused:
            allocate_assets(repository, FixedClock(), command)
        postgres_session.rollback()

        assert refused.value.detail == {
            "product_model_id": str(booked.product_model.id),
            "branch_id": str(booked.branch.id),
            "period": OVERLAPPING_HIRE.as_postgres_daterange(),
            "requested_quantity": 1,
            "constraint_name": OVERLAP_CONSTRAINT_NAME,
        }

    def test_the_refused_allocation_is_not_stored(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        repository = SqlAssetRepository(postgres_session)
        with pytest.raises(AllocationConflictError):
            repository.save_allocations([an_allocation_of(booked, OVERLAPPING_HIRE)])
        postgres_session.rollback()
        assert count_active_allocations(postgres_session, booked.asset.id) == 1

    def test_an_allocation_that_does_not_overlap_is_simply_written(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        adjacent = BookingPeriod(date(2026, 3, 12), date(2026, 3, 15))
        SqlAssetRepository(postgres_session).save_allocations([an_allocation_of(booked, adjacent)])
        postgres_session.commit()
        assert count_active_allocations(postgres_session, booked.asset.id) == 2


class TestAnyOtherIntegrityErrorIsNotSwallowed:
    """A different fault is a defect, and it must reach whoever can fix it."""

    def test_a_foreign_key_violation_is_raised_as_it_is(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        orphan = AssetAllocation(
            reservation_line_id=uuid4(),
            asset_id=booked.asset.id,
            branch_id=booked.branch.id,
            period=BookingPeriod(date(2026, 4, 1), date(2026, 4, 3)),
            allocated_at=ALLOCATED_AT,
        )
        with pytest.raises(IntegrityError) as raised:
            SqlAssetRepository(postgres_session).save_allocations([orphan])
        postgres_session.rollback()

        assert sqlstate_of(raised.value) == FOREIGN_KEY_VIOLATION_SQLSTATE
        assert constraint_name_of(raised.value) != OVERLAP_CONSTRAINT_NAME

    def test_a_check_violation_on_the_same_table_is_raised_as_it_is(
        self, postgres_session: Session, booked: AllocationScenario
    ) -> None:
        """Bypassing the entity, as a hand written script would, to reach the check."""
        half_released = an_allocation_of(booked, BookingPeriod(date(2026, 4, 1), date(2026, 4, 3)))
        # Set after construction, because the entity itself refuses this state.
        half_released.release_reason = ReleaseReason.CANCELLED
        with pytest.raises(IntegrityError) as raised:
            SqlAssetRepository(postgres_session).save_allocations([half_released])
        postgres_session.rollback()

        assert sqlstate_of(raised.value) == CHECK_VIOLATION_SQLSTATE
        assert constraint_name_of(raised.value) == RELEASE_STATE_CONSTRAINT_NAME
