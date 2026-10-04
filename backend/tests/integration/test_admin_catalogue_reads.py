"""The admin catalogue's reads on PostgreSQL, their statements and the indexes they stand on.

A list is two statements however many rows it holds, the count and the page,
and one category or one model is one. The count of the models of a category
and the count of the units of a model are correlated counts, one probe of an
index for each row of the page, so neither adds a statement. Each filter of
the model list, and each of those counts, is explained with sequential scans
switched off on tables that have been analysed, which shows whether the
condition matches the index it was written for. The four unique constraints
the repositories recognise exist under the names `schema_ddl` gives them.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.application.catalogue.admin_read_models import AdminCategorySearch, AdminModelSearch
from app.infrastructure.admin_catalogue_query import SqlAdminCatalogue
from app.infrastructure.models import Category
from app.infrastructure.schema_ddl import (
    ASSET_MODEL_INDEX,
    CATEGORY_CODE_CONSTRAINT_NAME,
    CATEGORY_SLUG_CONSTRAINT_NAME,
    PRODUCT_MODEL_CATEGORY_INDEX,
    PRODUCT_MODEL_PUBLISHED_INDEX,
    PRODUCT_MODEL_SKU_CONSTRAINT_NAME,
    PRODUCT_MODEL_SLUG_CONSTRAINT_NAME,
)
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

FEW: Final[int] = 3
MANY: Final[int] = 30
MODELS_PER_CATEGORY: Final[int] = 8
EXPLAIN_PREFIX: Final[str] = "EXPLAIN "
LIST_STATEMENTS: Final[int] = 2
ONE_STATEMENT: Final[int] = 1

MODELS_OF_A_CATEGORY: Final[str] = (
    "SELECT id FROM product_model WHERE category_id = :category ORDER BY name, sku LIMIT 20"
)
PUBLISHED_OF_A_CATEGORY: Final[str] = (
    "SELECT id FROM product_model WHERE category_id = :category AND is_published = true "
    "ORDER BY name LIMIT 20"
)
UNITS_OF_A_MODEL: Final[str] = "SELECT count(*) FROM asset WHERE product_model_id = :model"
MODELS_COUNTED: Final[str] = "SELECT count(*) FROM product_model WHERE category_id = :category"
CONSTRAINT_NAMES: Final[str] = (
    "SELECT conname FROM pg_constraint WHERE contype = 'u' AND conrelid IN "
    "('category'::regclass, 'product_model'::regclass)"
)


def stocked(session: Session, factory: Factory, categories: int) -> list[Category]:
    """Commit categories, each holding models with units at one branch, and analyse the tables."""
    branch = factory.branch()
    rows: list[Category] = []
    for number in range(categories):
        category = a_category(factory, name=f"Category {number:03d}", sort_order=number)
        for model_number in range(MODELS_PER_CATEGORY):
            model = a_model(
                factory,
                name=f"Model {number:03d}-{model_number}",
                category=category,
                is_published=bool(model_number % 2),
            )
            factory.asset(product_model=model, branch=branch)
        rows.append(category)
    session.commit()
    for table in ("category", "product_model", "asset"):
        session.execute(text(f"ANALYZE {table}"))
    session.commit()
    return rows


def plan_of(session: Session, statement: str, **params: object) -> str:
    """Return the plan of a statement with sequential scans switched off, to see the choice."""
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = session.execute(text(EXPLAIN_PREFIX + statement), params).all()
    return "\n".join(str(row[0]) for row in plan)


class TestTheStatementsDoNotGrowWithTheRows:
    """A list is two statements and one row is one, however much the catalogue holds."""

    @pytest.mark.parametrize("categories", [FEW, MANY])
    def test_the_category_list_is_two_statements(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        categories: int,
    ) -> None:
        stocked(postgres_session, postgres_factory, categories)
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as sent:
            page = SqlAdminCatalogue(reader).category_page(AdminCategorySearch())
        assert (len(page.items), len(sent)) == (categories, LIST_STATEMENTS)
        assert {entry.model_count for entry in page.items} == {MODELS_PER_CATEGORY}

    @pytest.mark.parametrize("categories", [FEW, MANY])
    def test_the_model_list_is_two_statements(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        categories: int,
    ) -> None:
        stocked(postgres_session, postgres_factory, categories)
        search = AdminModelSearch(
            text="model", category_id=None, published=None, page=1, page_size=100
        )
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as sent:
            page = SqlAdminCatalogue(reader).model_page(search)
        assert (page.total, len(sent)) == (categories * MODELS_PER_CATEGORY, LIST_STATEMENTS)
        assert {entry.asset_count for entry in page.items} == {1}

    def test_one_category_and_one_model_are_one_statement_each(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        (category,) = stocked(postgres_session, postgres_factory, 1)
        with Session(postgres_engine) as reader:
            catalogue = SqlAdminCatalogue(reader)
            first = catalogue.model_page(
                AdminModelSearch(
                    text=None, category_id=category.id, published=True, page=1, page_size=1
                )
            ).items[0]
            with recorded_statements(postgres_engine) as sent:
                found_category = catalogue.category(category.id)
                found_model = catalogue.model(first.id)
        assert found_category is not None and found_model is not None
        assert (len(sent), found_model.is_published) == (2 * ONE_STATEMENT, True)


class TestEachReadStandsOnItsIndex:
    """The planner can answer each filter and each count from the index written for it."""

    def test_the_models_of_a_category_are_found_through_the_index_of_0009(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        category = stocked(postgres_session, postgres_factory, MANY)[0]
        plan = plan_of(postgres_session, MODELS_OF_A_CATEGORY, category=category.id)
        assert PRODUCT_MODEL_CATEGORY_INDEX in plan, plan

    def test_the_published_models_of_a_category_are_found_through_a_category_index(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        category = stocked(postgres_session, postgres_factory, MANY)[0]
        plan = plan_of(postgres_session, PUBLISHED_OF_A_CATEGORY, category=category.id)
        assert PRODUCT_MODEL_PUBLISHED_INDEX in plan or PRODUCT_MODEL_CATEGORY_INDEX in plan, plan

    def test_the_models_of_a_category_are_counted_through_the_index_of_0009(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        category = stocked(postgres_session, postgres_factory, MANY)[0]
        plan = plan_of(postgres_session, MODELS_COUNTED, category=category.id)
        assert PRODUCT_MODEL_CATEGORY_INDEX in plan, plan

    def test_the_units_of_a_model_are_counted_through_the_index_of_0004(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        stocked(postgres_session, postgres_factory, MANY)
        model_id = postgres_session.execute(text("SELECT id FROM product_model LIMIT 1")).scalar()
        plan = plan_of(postgres_session, UNITS_OF_A_MODEL, model=model_id)
        assert ASSET_MODEL_INDEX in plan, plan


def test_the_unique_constraints_carry_the_names_the_repositories_recognise(
    postgres_session: Session,
) -> None:
    names = set(postgres_session.execute(text(CONSTRAINT_NAMES)).scalars())
    assert {
        CATEGORY_CODE_CONSTRAINT_NAME,
        CATEGORY_SLUG_CONSTRAINT_NAME,
        PRODUCT_MODEL_SKU_CONSTRAINT_NAME,
        PRODUCT_MODEL_SLUG_CONSTRAINT_NAME,
    } <= names
