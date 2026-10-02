"""How a constraint violation becomes a booking conflict, with no database.

Two steps are pinned here. `SqlAssetRepository.translate_integrity_error`
decides whether an integrity error is the overlap constraint firing, and it
decides on the SQLSTATE and the constraint name together. The allocation code
in the application layer then adds what was being asked for.

The errors are built by hand so that every combination can be tried, including
ones PostgreSQL cannot be made to produce on demand. The real violation, raised
by a real database, is in tests/integration/test_allocation_conflict_translation.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.application.availability.allocation import AllocationCommand, allocate_assets
from app.domain.availability import AssetAllocation
from app.domain.catalogue import Asset
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod
from app.infrastructure.availability import EXCLUSION_VIOLATION_SQLSTATE, SqlAssetRepository
from app.infrastructure.schema_ddl import OVERLAP_CONSTRAINT_NAME
from tests.support.clock import FixedClock

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
FOREIGN_KEY_VIOLATION_SQLSTATE: Final[str] = "23503"
SOME_OTHER_EXCLUSION_CONSTRAINT: Final[str] = "branch_opening_hours_no_overlap"
STATEMENT: Final[str] = "INSERT INTO asset_allocation ..."


@dataclass(frozen=True)
class _Diagnostics:
    """The part of a driver's diagnostics the translation reads."""

    constraint_name: str | None


class _Psycopg3Error(Exception):
    """A driver error shaped like psycopg 3, which exposes `sqlstate` and `diag`."""

    def __init__(self, sqlstate: str | None, constraint_name: str | None) -> None:
        """Carry the SQLSTATE and the constraint name the way the driver does."""
        super().__init__("a driver message that must never be parsed")
        self.sqlstate = sqlstate
        self.diag = _Diagnostics(constraint_name)


class _Psycopg2Error(Exception):
    """A driver error shaped like psycopg 2, which exposes `pgcode` instead."""

    def __init__(self, pgcode: str, constraint_name: str | None) -> None:
        """Carry the code under the older attribute name."""
        super().__init__("a driver message that must never be parsed")
        self.pgcode = pgcode
        self.diag = _Diagnostics(constraint_name)


def integrity_error(original: Exception) -> IntegrityError:
    """Wrap a driver error the way SQLAlchemy wraps one raised by a flush."""
    return IntegrityError(STATEMENT, None, original)


@pytest.fixture
def repository() -> SqlAssetRepository:
    """Return a repository over a session bound to no database. Translation uses none."""
    return SqlAssetRepository(Session())


class TestWhichIntegrityErrorsAreABookingConflict:
    """SQLSTATE 23P01 on the overlap constraint, and nothing else."""

    def test_an_exclusion_violation_on_the_overlap_constraint_is_a_conflict(
        self, repository: SqlAssetRepository
    ) -> None:
        error = integrity_error(
            _Psycopg3Error(EXCLUSION_VIOLATION_SQLSTATE, OVERLAP_CONSTRAINT_NAME)
        )
        conflict = repository.translate_integrity_error(error)
        assert isinstance(conflict, AllocationConflictError)
        assert conflict.detail == {"constraint_name": OVERLAP_CONSTRAINT_NAME}

    def test_the_older_driver_attribute_is_read_as_well(
        self, repository: SqlAssetRepository
    ) -> None:
        error = integrity_error(
            _Psycopg2Error(EXCLUSION_VIOLATION_SQLSTATE, OVERLAP_CONSTRAINT_NAME)
        )
        assert isinstance(repository.translate_integrity_error(error), AllocationConflictError)

    def test_an_exclusion_violation_on_a_different_constraint_is_not(
        self, repository: SqlAssetRepository
    ) -> None:
        """The SQLSTATE alone is not enough. Another exclusion constraint is another fault."""
        error = integrity_error(
            _Psycopg3Error(EXCLUSION_VIOLATION_SQLSTATE, SOME_OTHER_EXCLUSION_CONSTRAINT)
        )
        assert repository.translate_integrity_error(error) is None

    def test_an_exclusion_violation_naming_no_constraint_is_not(
        self, repository: SqlAssetRepository
    ) -> None:
        error = integrity_error(_Psycopg3Error(EXCLUSION_VIOLATION_SQLSTATE, None))
        assert repository.translate_integrity_error(error) is None

    def test_a_different_sqlstate_on_the_overlap_constraint_is_not(
        self, repository: SqlAssetRepository
    ) -> None:
        error = integrity_error(
            _Psycopg3Error(FOREIGN_KEY_VIOLATION_SQLSTATE, OVERLAP_CONSTRAINT_NAME)
        )
        assert repository.translate_integrity_error(error) is None

    def test_an_error_carrying_no_diagnostics_at_all_is_not(
        self, repository: SqlAssetRepository
    ) -> None:
        """What SQLite raises. It has no SQLSTATE, so it can never read as a conflict."""
        assert repository.translate_integrity_error(integrity_error(Exception("no codes"))) is None

    def test_the_driver_message_is_never_what_decides(
        self, repository: SqlAssetRepository
    ) -> None:
        misleading = _Psycopg3Error(FOREIGN_KEY_VIOLATION_SQLSTATE, "fk_asset_allocation_asset")
        misleading.args = (f"conflicting key value violates {OVERLAP_CONSTRAINT_NAME} 23P01",)
        assert repository.translate_integrity_error(integrity_error(misleading)) is None


class _RefusingAssets:
    """An asset port whose insert is refused the way the repository refuses one."""

    def __init__(self, asset: Asset) -> None:
        """Offer one unit, and refuse to keep an allocation of it."""
        self._asset = asset

    def lock_allocatable(
        self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
    ) -> list[Asset]:
        """Report the unit as free, as a pre check that lost the race would."""
        return [self._asset]

    def save_allocations(self, allocations: Sequence[AssetAllocation]) -> None:
        """Refuse, as the repository does when the constraint fires."""
        raise AllocationConflictError(
            "The database refused an allocation.", constraint_name=OVERLAP_CONSTRAINT_NAME
        )


class TestTheApplicationAddsWhatWasBeingAskedFor:
    """The repository knows the constraint fired. The caller needs to know for what."""

    def test_the_conflict_names_the_model_the_branch_the_period_and_the_quantity(self) -> None:
        asset = Asset(
            id=uuid4(),
            asset_tag="TSH-DR-0042",
            product_model_id=uuid4(),
            branch_id=uuid4(),
            status=AssetStatus.AVAILABLE,
            condition_grade=ConditionGrade.A,
        )
        command = AllocationCommand(
            reservation_line_id=uuid4(),
            product_model_id=asset.product_model_id,
            branch_id=asset.branch_id,
            period=FIRST_HIRE,
            quantity=1,
        )
        with pytest.raises(AllocationConflictError) as refused:
            allocate_assets(_RefusingAssets(asset), FixedClock(), command)
        assert refused.value.detail == {
            "product_model_id": str(asset.product_model_id),
            "branch_id": str(asset.branch_id),
            "period": FIRST_HIRE.as_postgres_daterange(),
            "requested_quantity": 1,
            "constraint_name": OVERLAP_CONSTRAINT_NAME,
        }
        assert isinstance(refused.value.__cause__, AllocationConflictError)
