"""The asset register's reads on PostgreSQL, and the statements each takes.

A page of the register is two statements however many units it holds, the
count and the page, and one unit is one. A unit's history is four statements
however long the unit has been in the fleet, one for each place its life is
recorded, and each reads at most fifty rows. That each condition stands on
its index is in tests/integration/test_asset_register_indexes.py.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.application.catalogue.asset_history import HISTORY_LIMIT, history_of
from app.application.catalogue.asset_read_models import AdminAssetSearch
from app.domain.enums import AssetStatus
from app.infrastructure.asset_register_query import SqlAssetRegister
from app.infrastructure.models import ProductModel
from tests.support.factories import Factory
from tests.support.register_pg import lived_in, stocked_units
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

FEW: Final[int] = 3
MANY: Final[int] = 60
LIST_STATEMENTS: Final[int] = 2
ONE_STATEMENT: Final[int] = 1
HISTORY_STATEMENTS: Final[int] = 4


def search(text_: str | None = None, **changes: object) -> AdminAssetSearch:
    """Return a search of the register for one page of a hundred."""
    values: dict[str, object] = {
        "text": text_,
        "branch_id": None,
        "status": None,
        "model_id": None,
        "page": 1,
        "page_size": 100,
        **changes,
    }
    return AdminAssetSearch(**values)


class TestTheStatementsDoNotGrowWithTheRows:
    """A page is two statements, a unit one and its history four, however much there is."""

    @pytest.mark.parametrize("units", [FEW, MANY])
    def test_a_page_is_two_statements_with_every_filter(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        units: int,
    ) -> None:
        branch, rows = stocked_units(postgres_session, postgres_factory, units)
        wanted = search(
            "sn-0",
            branch_id=branch.id,
            status=AssetStatus.AVAILABLE,
            model_id=rows[0].product_model_id,
        )
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as sent:
            page = SqlAssetRegister(reader).page(wanted)
        assert (page.total, len(sent)) == ((units + 1) // 2, LIST_STATEMENTS)
        assert {entry.active_allocation_count for entry in page.items} == {0}

    @pytest.mark.parametrize("times", [FEW, MANY])
    def test_one_unit_is_one_statement_and_its_history_four(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        times: int,
    ) -> None:
        _, rows = stocked_units(postgres_session, postgres_factory, FEW)
        unit = rows[0]
        model = postgres_session.get(ProductModel, unit.product_model_id)
        assert model is not None
        lived_in(postgres_session, postgres_factory, unit, model, times)
        tag, unit_id = unit.asset_tag, UUID(str(unit.id))
        with Session(postgres_engine) as reader:
            register = SqlAssetRegister(reader)
            register.branch_id_of("CBD")
            with recorded_statements(postgres_engine) as sent_for_unit:
                entry = register.unit(tag)
            with recorded_statements(postgres_engine) as sent_for_history:
                facts = register.history(unit_id, HISTORY_LIMIT)
        assert entry is not None
        assert (len(sent_for_unit), len(sent_for_history)) == (ONE_STATEMENT, HISTORY_STATEMENTS)
        read = min(times, HISTORY_LIMIT)
        assert (len(facts.allocations), len(facts.hires)) == (read, read)
        assert (len(facts.damage_reports), len(facts.audit_events)) == (read, read)
        history = history_of(facts)
        assert len(history) == min(7 * times, HISTORY_LIMIT)
