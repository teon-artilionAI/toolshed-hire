"""The GiST exclusion constraint, which is the reason this system is correct.

This is the most important test file in the repository. Everything else in the
availability path is a convenience. The constraint is the only thing that is
true under concurrency, after a deployment, and when somebody writes to the
database by hand at a counter, and if it is ever dropped or weakened then no
amount of application code makes double booking impossible again.

Five statements are proved, in the order a reader should meet them.

1. `btree_gist` exists after the migration. Without it the constraint cannot be
   created at all, because a GiST index cannot mix `asset_id WITH =` and
   `daterange(...) WITH &&` without it.
2. An overlapping active allocation of the same asset is rejected, with
   SQLSTATE 23P01 and the constraint name the application looks for.
3. A period that begins on the day the previous one ends is accepted, which is
   the half open rule enforced at the database rather than in Python.
4. A released allocation does not block anything. A cancelled booking must give
   its stock back, and it does so by carrying `released_at`, which drops it out
   of the constraint's partial index while leaving the history intact.
5. The same period on a different asset is accepted, because the constraint is
   about a physical unit and not about a catalogue entry.

The SQLSTATE is asserted from the driver's own diagnostics. The error message is
never parsed, because a message changes with a PostgreSQL release or a locale,
and a control decision built on one is how a 409 silently becomes a 500.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.application.allocate import AllocationCommand, allocate_assets
from app.domain.enums import AllocationStatus
from app.domain.errors import AssetUnavailableConflict
from app.domain.period import BookingPeriod
from app.infrastructure.schema_ddl import (
    OVERLAP_CONSTRAINT_NAME,
    RELEASE_STATE_CONSTRAINT_NAME,
    REQUIRED_EXTENSIONS,
)
from tests.support.factories import Factory
from tests.support.pg import (
    CHECK_VIOLATION_SQLSTATE,
    EXCLUSION_VIOLATION_SQLSTATE,
    constraint_name_of,
    count_active_allocations,
    exclusion_constraint_names,
    installed_extensions,
    sqlstate_of,
)
from tests.support.scenarios import build_allocation_scenario

pytestmark = pytest.mark.postgres

ALLOCATIONS_TABLE = "asset_allocations"
# The worked example month. The ninth to the twelfth ends on the twelfth, and
# the twelfth to the fifteenth starts on it.
NINTH = date(2026, 3, 9)
TWELFTH = date(2026, 3, 12)
FIFTEENTH = date(2026, 3, 15)
FIRST_HIRE = BookingPeriod(NINTH, TWELFTH)
ADJACENT_HIRE = BookingPeriod(TWELFTH, FIFTEENTH)
OVERLAPPING_HIRE = BookingPeriod(date(2026, 3, 11), FIFTEENTH)
EARLIER_ADJACENT_HIRE = BookingPeriod(date(2026, 3, 6), NINTH)


class TestTheMigrationCreatesWhatTheConstraintNeeds:
    """A missing extension or a missing constraint is a silent loss of the invariant."""

    def test_btree_gist_is_installed_after_the_migration(self, postgres_session: Session) -> None:
        assert "btree_gist" in installed_extensions(postgres_session)

    def test_every_extension_the_schema_declares_is_installed(
        self, postgres_session: Session
    ) -> None:
        assert set(REQUIRED_EXTENSIONS) <= installed_extensions(postgres_session)

    def test_the_overlap_constraint_exists_on_asset_allocations_under_its_expected_name(
        self, postgres_session: Session
    ) -> None:
        names = exclusion_constraint_names(postgres_session, ALLOCATIONS_TABLE)
        assert OVERLAP_CONSTRAINT_NAME in names, (
            "The exclusion constraint the whole design depends on is absent. Found "
            f"exclusion constraints {sorted(names)} on {ALLOCATIONS_TABLE}."
        )


class TestOverlapIsRejected:
    """The defining behaviour: one physical unit, one hirer, at any one time."""

    def test_a_second_active_allocation_overlapping_the_first_is_rejected(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        postgres_session.flush()

        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=OVERLAPPING_HIRE
            )
        )
        with pytest.raises(IntegrityError) as raised:
            postgres_session.flush()
        postgres_session.rollback()

        assert sqlstate_of(raised.value) == EXCLUSION_VIOLATION_SQLSTATE
        assert constraint_name_of(raised.value) == OVERLAP_CONSTRAINT_NAME

    def test_an_identical_period_on_the_same_asset_is_rejected(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        postgres_session.flush()

        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        with pytest.raises(IntegrityError) as raised:
            postgres_session.flush()
        postgres_session.rollback()
        assert sqlstate_of(raised.value) == EXCLUSION_VIOLATION_SQLSTATE

    def test_the_use_case_refuses_an_overlapping_request_as_an_asset_unavailable_conflict(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """The pre check answers first here, which is what gives a useful message.

        The path where the constraint itself answers is proved under genuine
        concurrency in test_concurrent_allocation.py.
        """
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        postgres_session.commit()

        with pytest.raises(AssetUnavailableConflict) as raised:
            allocate_assets(
                postgres_session,
                AllocationCommand(
                    reservation_line_id=scenario.line.id,
                    product_model_id=scenario.product_model.id,
                    branch_id=scenario.branch.id,
                    period=OVERLAPPING_HIRE,
                    quantity=1,
                ),
            )
        assert raised.value.detail["period"] == OVERLAPPING_HIRE.as_postgres_daterange()
        assert raised.value.detail["available_quantity"] == 0


class TestTheHalfOpenBoundaryHoldsAtTheDatabase:
    """A return on the twelfth frees the twelfth, in SQL and not only in Python."""

    def test_a_hire_starting_on_the_day_the_previous_one_ends_is_accepted(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=ADJACENT_HIRE
            )
        )
        postgres_session.commit()
        assert count_active_allocations(postgres_session, scenario.asset.id) == 2

    def test_a_hire_ending_on_the_day_the_next_one_begins_is_accepted(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=EARLIER_ADJACENT_HIRE
            )
        )
        postgres_session.commit()
        assert count_active_allocations(postgres_session, scenario.asset.id) == 2


class TestReleasedAllocationsGiveTheirStockBack:
    """A cancellation must free the unit, and must not delete the history that it happened."""

    def test_a_released_allocation_does_not_block_the_same_asset_on_the_same_dates(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        cancelled = postgres_factory.allocation(
            line=scenario.line,
            asset=scenario.asset,
            period=FIRST_HIRE,
            status=AllocationStatus.CANCELLED,
            released_at=datetime.now(UTC),
        )
        postgres_session.add(cancelled)
        postgres_session.flush()

        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line, asset=scenario.asset, period=FIRST_HIRE
            )
        )
        postgres_session.commit()
        assert count_active_allocations(postgres_session, scenario.asset.id) == 1

    def test_a_released_allocation_stays_in_the_table_as_history(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        cancelled = postgres_factory.allocation(
            line=scenario.line,
            asset=scenario.asset,
            period=FIRST_HIRE,
            status=AllocationStatus.CANCELLED,
            released_at=datetime.now(UTC),
        )
        postgres_session.add(cancelled)
        postgres_session.commit()
        stored = postgres_session.get(type(cancelled), cancelled.id)
        assert stored is not None
        assert stored.status is AllocationStatus.CANCELLED

    def test_an_allocation_cannot_claim_a_released_status_without_a_release_timestamp(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE)
        postgres_session.add(
            postgres_factory.allocation(
                line=scenario.line,
                asset=scenario.asset,
                period=FIRST_HIRE,
                status=AllocationStatus.CANCELLED,
                released_at=None,
            )
        )
        with pytest.raises(IntegrityError) as raised:
            postgres_session.flush()
        postgres_session.rollback()
        assert sqlstate_of(raised.value) == CHECK_VIOLATION_SQLSTATE
        assert constraint_name_of(raised.value) == RELEASE_STATE_CONSTRAINT_NAME


class TestTheConstraintIsPerPhysicalUnit:
    """Availability is a fact about a tagged asset, not about a catalogue entry."""

    def test_the_same_period_on_a_different_asset_is_accepted(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE, asset_count=2)
        first, second = scenario.assets
        postgres_session.add(
            postgres_factory.allocation(line=scenario.line, asset=first, period=FIRST_HIRE)
        )
        postgres_session.add(
            postgres_factory.allocation(line=scenario.line, asset=second, period=FIRST_HIRE)
        )
        postgres_session.commit()
        assert count_active_allocations(postgres_session, first.id) == 1
        assert count_active_allocations(postgres_session, second.id) == 1
