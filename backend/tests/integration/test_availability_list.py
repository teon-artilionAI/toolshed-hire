"""The availability search as a list, with its filters, its pages and its cost.

`GET /api/catalogue/availability` lists the same models the catalogue lists,
in the same orders, and adds an answer from every branch. These tests prove
the filters still apply once the list is cut into a page inside the statement,
that the branch filter keeps only models free at that branch, and two things
about cost that NFR-01 depends on.

The first is that a page is answered by a fixed number of statements, however
many models it holds. The statements are counted as they reach the database.

The second is that the statement can use the two indexes it was written for.
On a database this small the planner would rather read a table from end to
end, so the plan is asked for with sequential scans switched off. That shows
whether the expressions in the statement match the indexes, which is the part
a careless edit would break.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, select

from app.application.availability.read_models import AvailabilitySearch
from app.application.catalogue.read_models import ModelSearch
from app.domain.period import BookingPeriod
from app.infrastructure.availability_search import availability_page_statement
from app.infrastructure.models import Branch
from app.infrastructure.schema_ddl import OVERLAP_CONSTRAINT_NAME
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    a_category,
    a_model,
    hold_unit,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.log_capture import LogCapture
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
PERIOD: Final[dict[str, object]] = {"from": "2026-03-09", "to": "2026-03-12"}
AVAILABLE_UNIT_INDEX: Final[str] = "ix_asset_available"
SEARCH_FINISHED: Final[str] = "availability.search_finished"
# The two halves of the sweep, which lapse expired holds and mark no shows,
# the count and the page (BR-13, BR-17).
STATEMENTS_OF_A_PLAIN_SEARCH: Final[int] = 4
# A category and a branch each add one lookup.
MOST_STATEMENTS_A_SEARCH_MAY_ISSUE: Final[int] = STATEMENTS_OF_A_PLAIN_SEARCH + 2
LARGEST_PAGE: Final[int] = 50


@pytest.fixture
def visitor(postgres_session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the real database."""
    with visitor_client(postgres_session) as client:
        yield client


@pytest.fixture
def yard(postgres_session: Session, postgres_factory: Factory) -> None:
    """Commit two branches and four published models, some of them held.

    For the ninth to the twelfth of March the answers are these.

    | Model            | Bellville | Somerset West |
    |------------------|-----------|---------------|
    | Chain Hoist      | free      | no unit       |
    | Extension Ladder | held      | free          |
    | Plate Compactor  | free      | free          |
    | Trench Rammer    | no unit   | held          |
    """
    bellville = postgres_factory.branch(code="BLV", name="Bellville")
    somerset_west = postgres_factory.branch(code="SMW", name="Somerset West")
    access = a_category(postgres_factory, name="Access and Lifting", sort_order=60)
    ladders = a_category(postgres_factory, name="Ladders", sort_order=61, parent=access)
    compaction = a_category(postgres_factory, name="Compaction", sort_order=20)
    wacker = "Wacker Neuson"

    hoist = a_model(postgres_factory, name="Chain Hoist", category=access, daily_rate="310.00")
    ladder = a_model(
        postgres_factory, name="Extension Ladder", category=ladders, daily_rate="95.00"
    )
    compactor = a_model(
        postgres_factory,
        name="Plate Compactor",
        category=compaction,
        manufacturer=wacker,
        daily_rate="420.00",
    )
    rammer = a_model(
        postgres_factory,
        name="Trench Rammer",
        category=compaction,
        manufacturer=wacker,
        daily_rate="380.00",
    )
    draft = a_model(
        postgres_factory, name="Unreleased Roller", category=compaction, is_published=False
    )

    postgres_factory.asset(product_model=hoist, branch=bellville)
    held_ladder = postgres_factory.asset(product_model=ladder, branch=bellville)
    postgres_factory.asset(product_model=ladder, branch=somerset_west)
    postgres_factory.asset(product_model=compactor, branch=bellville)
    postgres_factory.asset(product_model=compactor, branch=somerset_west)
    held_rammer = postgres_factory.asset(product_model=rammer, branch=somerset_west)
    postgres_factory.asset(product_model=draft, branch=bellville)
    hold_unit(postgres_factory, held_ladder, HIRE)
    hold_unit(postgres_factory, held_rammer, HIRE)
    postgres_session.commit()


def listed(visitor: TestClient, **params: object) -> dict[str, object]:
    """Return the body of an availability search for the standard period."""
    response = visitor.get(AVAILABILITY_PATH, params={**PERIOD, **params})
    assert response.status_code == status.HTTP_200_OK, response.text
    body: dict[str, object] = response.json()
    return body


def free_at(body: dict[str, object]) -> dict[str, list[str]]:
    """Return the branch codes each listed model is free at, by model name."""
    items = body["items"]
    assert isinstance(items, list)
    return {
        item["model"]["name"]: [
            answer["branchCode"] for answer in item["branches"] if answer["available"]
        ]
        for item in items
    }


@pytest.mark.usefixtures("yard")
class TestTheList:
    """Every published model, every branch, in the order asked for."""

    def test_every_published_model_is_answered_for_at_every_branch(
        self, visitor: TestClient
    ) -> None:
        body = listed(visitor)
        assert body["total"] == 4
        assert free_at(body) == {
            "Chain Hoist": ["BLV"],
            "Extension Ladder": ["SMW"],
            "Plate Compactor": ["BLV", "SMW"],
            "Trench Rammer": [],
        }

    def test_the_branches_come_in_the_same_order_under_every_model(
        self, visitor: TestClient
    ) -> None:
        items = listed(visitor)["items"]
        assert isinstance(items, list)
        orders = {tuple(answer["branchCode"] for answer in item["branches"]) for item in items}
        assert orders == {("BLV", "SMW")}

    def test_a_branch_keeps_only_the_models_free_there_and_the_total_follows(
        self, visitor: TestClient
    ) -> None:
        body = listed(visitor, branch="BLV")
        assert list(free_at(body)) == ["Chain Hoist", "Plate Compactor"]
        assert body["total"] == 2
        assert list(free_at(listed(visitor, branch="SMW"))) == [
            "Extension Ladder",
            "Plate Compactor",
        ]

    def test_a_page_is_cut_after_the_order_and_carries_the_total(
        self, visitor: TestClient
    ) -> None:
        second = listed(visitor, page=2, pageSize=3)
        assert (second["page"], second["pageSize"], second["total"]) == (2, 3, 4)
        assert free_at(second) == {"Trench Rammer": []}
        assert listed(visitor, page=3, pageSize=3)["items"] == []

    def test_a_parent_category_includes_its_children(
        self, visitor: TestClient, postgres_session: Session
    ) -> None:
        slugs = {
            item["name"]: item["slug"]
            for item in visitor.get("/api/catalogue/categories").json()["items"]
        }
        body = listed(visitor, category=slugs["Access and Lifting"])
        assert list(free_at(body)) == ["Chain Hoist", "Extension Ladder"]
        assert body["total"] == 2

    def test_the_text_search_narrows_the_list(self, visitor: TestClient) -> None:
        body = listed(visitor, q="WACKER")
        assert list(free_at(body)) == ["Plate Compactor", "Trench Rammer"]
        assert body["total"] == 2

    @pytest.mark.parametrize(
        ("sort", "expected"),
        [
            ("name", ["Chain Hoist", "Extension Ladder", "Plate Compactor", "Trench Rammer"]),
            (
                "dailyRateAsc",
                ["Extension Ladder", "Chain Hoist", "Trench Rammer", "Plate Compactor"],
            ),
            (
                "dailyRateDesc",
                ["Plate Compactor", "Trench Rammer", "Chain Hoist", "Extension Ladder"],
            ),
        ],
    )
    def test_each_sort_order(self, visitor: TestClient, sort: str, expected: list[str]) -> None:
        assert list(free_at(listed(visitor, sort=sort))) == expected

    def test_a_model_is_still_listed_when_no_branch_is_trading(
        self, visitor: TestClient, postgres_session: Session
    ) -> None:
        for branch in postgres_session.exec(select(Branch)).all():
            branch.is_active = False
            postgres_session.add(branch)
        postgres_session.commit()

        body = listed(visitor)

        assert body["total"] == 4
        assert free_at(body) == {
            "Chain Hoist": [],
            "Extension Ladder": [],
            "Plate Compactor": [],
            "Trench Rammer": [],
        }
        items = body["items"]
        assert isinstance(items, list)
        assert all(item["branches"] == [] for item in items)

    def test_the_search_is_logged_with_its_filters_its_rows_and_its_duration(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        listed(visitor, branch="BLV", q="wacker")
        line = application_log.only(SEARCH_FINISHED)
        assert line["period"] == "[2026-03-09,2026-03-12)"
        assert line["branch"] == "BLV"
        assert line["q_length"] == len("wacker")
        assert line["row_count"] == 2
        assert isinstance(line["duration_ms"], float)


@pytest.mark.usefixtures("yard")
class TestAPageCostsAFixedNumberOfStatements:
    """One statement answers the page, however many models are on it.

    A search also runs the sweep before it answers, which is one statement
    for each of its two halves when nothing is due and does not grow with the
    page either.
    """

    def test_the_count_does_not_grow_with_the_models_on_the_page(
        self,
        visitor: TestClient,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
    ) -> None:
        with recorded_statements(postgres_engine) as few_models:
            assert len(listed(visitor, pageSize=LARGEST_PAGE)["items"]) == 4

        for index in range(20):
            a_model(postgres_factory, name=f"Site Light {index:02d}")
        postgres_session.commit()

        with recorded_statements(postgres_engine) as many_models:
            assert len(listed(visitor, pageSize=LARGEST_PAGE)["items"]) == 24

        assert len(many_models) == len(few_models) == STATEMENTS_OF_A_PLAIN_SEARCH

    def test_a_category_and_a_branch_add_one_lookup_each_and_nothing_per_model(
        self, visitor: TestClient, postgres_engine: Engine
    ) -> None:
        slug = visitor.get("/api/catalogue/categories").json()["items"][0]["slug"]
        with recorded_statements(postgres_engine) as statements:
            listed(visitor, pageSize=LARGEST_PAGE, category=slug, branch="BLV", q="wacker")
        assert len(statements) == MOST_STATEMENTS_A_SEARCH_MAY_ISSUE


@pytest.mark.usefixtures("yard")
class TestTheStatementMatchesItsIndexes:
    """The partial index on available units and the GiST index of the constraint."""

    def test_the_plan_reads_both_indexes_once_sequential_scans_are_off(
        self, postgres_session: Session
    ) -> None:
        search = AvailabilitySearch(period=HIRE, models=ModelSearch(page_size=LARGEST_PAGE))
        statement = availability_page_statement(search)
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        connection = postgres_session.connection()
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        # The statement text is the application's own, compiled with its values
        # written in. Nothing in it came from a request.
        plan_lines = connection.exec_driver_sql("EXPLAIN " + sql).scalars()
        plan = "\n".join(str(line) for line in plan_lines)
        postgres_session.rollback()

        assert AVAILABLE_UNIT_INDEX in plan, plan
        assert OVERLAP_CONSTRAINT_NAME in plan, plan
        assert "&&" in plan, plan
