"""Each condition of the asset register's reads stands on its index, on PostgreSQL.

Each condition of a search and of a history is explained with sequential
scans switched off on tables analysed in the same transaction, which shows
whether it matches the index it was written for. The transaction is rolled
back, so the figures never reach the plans of another test. Revision 0010 built the two indexes the
register needed, the trigram index on the serial number and the btree on the
allocations a unit was released from. That a read takes the same statements
however much there is, is in tests/integration/test_asset_register_reads.py.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlmodel import Session

from app.infrastructure.models import ProductModel
from app.infrastructure.schema_ddl import (
    ALLOCATION_RELEASED_INDEX,
    ASSET_MODEL_INDEX,
    ASSET_SERIAL_SEARCH_INDEX,
    ASSET_TAG_SEARCH_INDEX,
    AUDIT_ENTITY_ID_INDEX,
    AUDIT_ENTITY_INDEX,
    DAMAGE_REPORT_ASSET_INDEX,
    OVERLAP_CONSTRAINT_INDEX,
)
from tests.support.catalogue import hold_unit
from tests.support.checkout_api import TODAY_HIRE as HELD_FOR
from tests.support.factories import Factory
from tests.support.register_pg import lived_in, plan_of, stocked_units

pytestmark = pytest.mark.postgres

FEW: Final[int] = 3
MANY: Final[int] = 60
SERIAL_SEARCH: Final[str] = "SELECT id FROM asset WHERE serial_number ILIKE :pattern"
TAG_SEARCH: Final[str] = "SELECT id FROM asset WHERE asset_tag ILIKE :pattern"
UNITS_OF_A_MODEL: Final[str] = "SELECT id FROM asset WHERE product_model_id = :model"
RELEASED_ALLOCATIONS_OF_A_UNIT: Final[str] = (
    "SELECT id FROM asset_allocation WHERE asset_id = :unit AND released_at IS NOT NULL "
    "ORDER BY released_at DESC LIMIT 50"
)
ACTIVE_ALLOCATIONS_OF_A_UNIT: Final[str] = (
    "SELECT count(*) FROM asset_allocation WHERE asset_id = :unit AND released_at IS NULL"
)
OPEN_REPORTS_OF_A_UNIT: Final[str] = (
    "SELECT count(*) FROM damage_report WHERE asset_id = :unit "
    "AND status IN ('OPEN', 'UNDER_REPAIR')"
)
# Two indexes of the baseline, named as the baseline names them.
BRANCH_STATUS_INDEX: Final[str] = "ix_asset_branch_status"
RENTAL_ITEM_ASSET_INDEX: Final[str] = "ix_rental_item_asset"
UNITS_OF_A_BRANCH_IN_A_STATUS: Final[str] = (
    "SELECT count(*) FROM asset WHERE branch_id = :branch AND status = :status"
)
HIRES_OF_A_UNIT: Final[str] = "SELECT id FROM rental_item WHERE asset_id = :unit"
EVENTS_OF_A_UNIT: Final[str] = (
    "SELECT id FROM audit_event WHERE entity_id = :unit AND entity_type = 'asset' "
    "ORDER BY occurred_at DESC, id DESC LIMIT 50"
)


class TestEachReadStandsOnItsIndex:
    """The planner can answer each condition from the index written for it."""

    def test_part_of_a_serial_number_is_found_through_the_index_of_0010(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        stocked_units(postgres_session, postgres_factory, MANY)
        plan = plan_of(postgres_session, SERIAL_SEARCH, pattern="%00042%")
        assert ASSET_SERIAL_SEARCH_INDEX in plan, plan

    def test_part_of_a_tag_is_found_through_the_index_of_0004(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        stocked_units(postgres_session, postgres_factory, MANY)
        plan = plan_of(postgres_session, TAG_SEARCH, pattern="%DR-004%")
        assert ASSET_TAG_SEARCH_INDEX in plan, plan

    def test_the_units_of_a_model_are_found_through_the_index_of_0004(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, MANY)
        plan = plan_of(postgres_session, UNITS_OF_A_MODEL, model=rows[0].product_model_id)
        assert ASSET_MODEL_INDEX in plan, plan

    def test_the_released_allocations_of_a_unit_are_found_through_the_index_of_0010(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, FEW)
        model = postgres_session.get(ProductModel, rows[0].product_model_id)
        assert model is not None
        lived_in(postgres_session, postgres_factory, rows[0], model, MANY)
        plan = plan_of(postgres_session, RELEASED_ALLOCATIONS_OF_A_UNIT, unit=rows[0].id)
        assert ALLOCATION_RELEASED_INDEX in plan, plan

    def test_the_bookings_that_hold_a_unit_are_counted_through_the_constraint_index(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, MANY)
        for unit in rows:
            hold_unit(postgres_factory, unit, HELD_FOR)
        postgres_session.commit()
        plan = plan_of(postgres_session, ACTIVE_ALLOCATIONS_OF_A_UNIT, unit=rows[0].id)
        assert OVERLAP_CONSTRAINT_INDEX in plan, plan

    def test_the_open_reports_of_a_unit_are_counted_through_the_index_of_0005(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, FEW)
        model = postgres_session.get(ProductModel, rows[0].product_model_id)
        assert model is not None
        lived_in(postgres_session, postgres_factory, rows[0], model, MANY)
        plan = plan_of(postgres_session, OPEN_REPORTS_OF_A_UNIT, unit=rows[0].id)
        assert DAMAGE_REPORT_ASSET_INDEX in plan, plan

    def test_the_events_of_a_unit_are_read_through_an_index_on_its_key(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, FEW)
        model = postgres_session.get(ProductModel, rows[0].product_model_id)
        assert model is not None
        lived_in(postgres_session, postgres_factory, rows[0], model, MANY)
        plan = plan_of(postgres_session, EVENTS_OF_A_UNIT, unit=rows[0].id)
        assert AUDIT_ENTITY_ID_INDEX in plan or AUDIT_ENTITY_INDEX in plan, plan

    def test_the_units_of_a_branch_in_a_status_are_found_through_the_baseline_index(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        branch, _ = stocked_units(postgres_session, postgres_factory, MANY)
        plan = plan_of(
            postgres_session, UNITS_OF_A_BRANCH_IN_A_STATUS, branch=branch.id, status="QUARANTINED"
        )
        assert BRANCH_STATUS_INDEX in plan, plan

    def test_the_hires_of_a_unit_are_found_through_the_baseline_index(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, FEW)
        model = postgres_session.get(ProductModel, rows[0].product_model_id)
        assert model is not None
        lived_in(postgres_session, postgres_factory, rows[0], model, MANY)
        plan = plan_of(postgres_session, HIRES_OF_A_UNIT, unit=rows[0].id)
        assert RENTAL_ITEM_ASSET_INDEX in plan, plan
