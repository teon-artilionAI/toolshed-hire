"""Each statement of the counter's overview and locator stands on its index (FR-15, FR-16).

The rows are those of `tests/support/counter_pg.py`. On a database this small
the planner would rather read a table from end to end, so each plan is asked
for with sequential scans switched off. That shows whether the expression in
the statement matches the index it was written for, which is the part a
careless edit would break. Every value in an explained statement is bound.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.infrastructure.schema_ddl import (
    ASSET_MODEL_INDEX,
    ASSET_TAG_SEARCH_INDEX,
    RENTAL_BRANCH_DUE_INDEX,
)
from tests.support.counter_pg import ONE_DAY, TODAY, Counter, build_counter
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

EXPLAIN_PREFIX: Final[str] = "EXPLAIN "
TAG_SEARCH: Final[str] = "SELECT id FROM asset WHERE asset_tag ILIKE :pattern"
UNITS_OF_A_MODEL: Final[str] = "SELECT id FROM asset WHERE product_model_id = :model"
HIRES_DUE_IN_A_RUN: Final[str] = (
    "SELECT id FROM rental WHERE branch_id = :branch AND due_back_on >= :first "
    "AND due_back_on <= :last"
)
COLLECTIONS_DUE: Final[str] = (
    "SELECT id FROM reservation WHERE branch_id = :branch AND status = 'CONFIRMED' "
    "AND start_date <= :today"
)
HIRES_OVERDUE: Final[str] = (
    "SELECT id FROM rental WHERE branch_id = :branch AND returned_at IS NULL "
    "AND due_back_on < :today"
)


@pytest.fixture
def counter(postgres_session: Session, postgres_factory: Factory) -> Counter:
    """Return a committed branch with collections, returns, an overdue hire and a quarantine."""
    return build_counter(postgres_session, postgres_factory)


def plan_of(session: Session, statement: str, **params: object) -> str:
    """Return the plan of a statement with sequential scans switched off, to see the choice."""
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = session.execute(text(EXPLAIN_PREFIX + statement), params).all()
    return "\n".join(str(row[0]) for row in plan)


class TestEachStatementStandsOnItsIndex:
    """The planner can answer each statement from the index it was written for."""

    def test_part_of_a_tag_is_found_through_the_trigram_index(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        plan = plan_of(postgres_session, TAG_SEARCH, pattern="%TS-00%")
        assert ASSET_TAG_SEARCH_INDEX in plan, plan

    def test_the_units_of_a_model_are_reached_by_their_model(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        plan = plan_of(postgres_session, UNITS_OF_A_MODEL, model=counter.mixer_id)
        assert ASSET_MODEL_INDEX in plan, plan

    def test_the_hires_due_back_on_a_past_day_are_found_through_the_branch_and_the_day(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        plan = plan_of(
            postgres_session,
            HIRES_DUE_IN_A_RUN,
            branch=counter.branch_id,
            first=TODAY - 6 * ONE_DAY,
            last=TODAY,
        )
        assert RENTAL_BRANCH_DUE_INDEX in plan, plan

    def test_the_collections_due_are_read_through_an_index_on_the_first_day(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        plan = plan_of(postgres_session, COLLECTIONS_DUE, branch=counter.branch_id, today=TODAY)
        assert "ix_reservation_confirmed_start" in plan or "ix_reservation_branch_start" in plan

    def test_the_hires_still_out_are_read_through_an_index_on_the_due_day(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        plan = plan_of(postgres_session, HIRES_OVERDUE, branch=counter.branch_id, today=TODAY)
        assert "ix_rental_open_due_back" in plan or RENTAL_BRANCH_DUE_INDEX in plan, plan
