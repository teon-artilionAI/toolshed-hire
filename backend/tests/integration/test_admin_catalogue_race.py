"""A code, a SKU or a slug two administrators race for, on PostgreSQL (FR-22).

A code, a SKU and a slug are unique, and the use case checks before it
writes. A second administrator can still take a value between the check and
the insert, and then the unique constraint refuses the row. Each of the four
constraints is recognised by its name and answered with the field it guards,
and the race is staged for real, with the first insert held open until the
second is provably waiting behind it. The answer names the field as the check
would have, and nothing of the losing write is kept.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Final
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.application.catalogue.admin_commands import NewCategoryCommand
from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.application.catalogue.manage_categories import CreateCategoryUseCase
from app.application.refusal import refused_parameter_of
from app.domain.catalogue_entry_rules import CatalogueEntry
from app.domain.category_rules import CatalogueCategory
from app.domain.enums import UserRole
from app.domain.errors import ValidationFailure
from app.domain.identity import Actor
from app.infrastructure.admin_catalogue_entries import SqlCatalogueEntryRepository
from app.infrastructure.admin_catalogue_query import SqlAdminCatalogue
from app.infrastructure.admin_categories import SqlCategoryRepository
from app.infrastructure.models import Category
from tests.support.booking import opening
from tests.support.catalogue import a_category
from tests.support.catalogue_terms import category_terms, model_terms
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.factories import Factory
from tests.support.race import backend_pid

pytestmark = pytest.mark.postgres

WAIT_SECONDS: Final[float] = 15.0
POLL_SECONDS: Final[float] = 0.02
BLOCKED_BY: Final[str] = (
    "SELECT count(*) FROM pg_stat_activity WHERE :holder = ANY(pg_blocking_pids(pid))"
)


@pytest.fixture
def reader(postgres_engine: Engine, postgres_session: Session) -> Iterator[Session]:
    """Yield a session of its own, closed before the tables are emptied again."""
    with Session(postgres_engine) as session:
        yield session


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> Actor:
    """Return a committed administrator, as the actor its audit events name."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return Actor(user_id=account.id, role=UserRole.ADMIN)


@pytest.fixture
def category(postgres_session: Session, postgres_factory: Factory) -> Category:
    """Commit an active category."""
    row = a_category(postgres_factory, name="Drilling")
    postgres_session.commit()
    return row


class TestTheUniqueConstraintsNameTheirField:
    """A row the unique constraint refuses is named by the field the constraint guards."""

    @pytest.mark.usefixtures("postgres_session")
    @pytest.mark.parametrize(
        ("taken", "field"), [({"code": "CAT-TAKEN"}, "code"), ({"slug": "taken"}, "slug")]
    )
    def test_a_category_that_repeats_a_held_value_names_it(
        self, postgres_engine: Engine, taken: dict[str, str], field: str
    ) -> None:
        held = CatalogueCategory(id=uuid4(), terms=category_terms(code="CAT-TAKEN", slug="taken"))
        values: dict[str, object] = {"code": "OTHER", "slug": "other", **taken}
        repeat = CatalogueCategory(id=uuid4(), terms=category_terms(**values))
        with Session(postgres_engine) as session:
            SqlCategoryRepository(session).add(held, DEFAULT_INSTANT)
            with pytest.raises(DuplicateCatalogueValue) as error:
                SqlCategoryRepository(session).add(repeat, DEFAULT_INSTANT)
        assert error.value.field == field

    @pytest.mark.parametrize(
        ("taken", "field"), [({"sku": "SKU-TAKEN"}, "sku"), ({"slug": "taken"}, "slug")]
    )
    def test_a_model_that_repeats_a_held_value_names_it(
        self, postgres_engine: Engine, category: Category, taken: dict[str, str], field: str
    ) -> None:
        held = CatalogueEntry(
            id=uuid4(),
            terms=model_terms(category.id, sku="SKU-TAKEN", slug="taken"),
            is_published=False,
        )
        values: dict[str, object] = {"sku": "SKU-OTHER", "slug": "other", **taken}
        repeat = CatalogueEntry(
            id=uuid4(), terms=model_terms(category.id, **values), is_published=False
        )
        with Session(postgres_engine) as session:
            SqlCatalogueEntryRepository(session).add(held, DEFAULT_INSTANT)
            with pytest.raises(DuplicateCatalogueValue) as error:
                SqlCatalogueEntryRepository(session).add(repeat, DEFAULT_INSTANT)
        assert error.value.field == field


def test_a_code_taken_between_the_check_and_the_insert_is_refused_naming_it(
    postgres_engine: Engine, reader: Session, administrator: Actor
) -> None:
    clock = FixedClock()
    with Session(postgres_engine) as holder:
        holder_pid = backend_pid(holder)
        holder.add(Category(code="PUMPS", name="Pumps", slug="pumps-held"))
        holder.flush()

        def second_administrator() -> object:
            use_case = CreateCategoryUseCase(
                opening(postgres_engine)(), clock, SqlAdminCatalogue(reader)
            )
            return use_case.execute(
                NewCategoryCommand(
                    actor=administrator,
                    code="PUMPS",
                    name="Pumps",
                    slug="pumps",
                    description=None,
                    parent_category_id=None,
                    sort_order=0,
                )
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(second_administrator)
            _wait_until_someone_waits_behind(postgres_engine, holder_pid)
            holder.commit()
            with pytest.raises(ValidationFailure) as error:
                pending.result(timeout=WAIT_SECONDS)
    assert (refused_parameter_of(error.value), error.value.message) == (
        "code",
        "Another category already has this code.",
    )
    with Session(postgres_engine) as check:
        assert [row.slug for row in check.exec(select(Category)).all()] == ["pumps-held"]
        assert check.execute(text("SELECT count(*) FROM audit_event")).scalar_one() == 0


def _wait_until_someone_waits_behind(engine: Engine, holder_pid: int) -> None:
    """Block until another backend is waiting on a lock the holder keeps.

    Each poll is a connection of its own, because the contents of
    `pg_stat_activity` hold still for the length of one transaction.
    """
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            if connection.execute(text(BLOCKED_BY), {"holder": holder_pid}).scalar_one():
                return
        time.sleep(POLL_SECONDS)
    raise AssertionError(
        f"Attempted to stage a race behind backend {holder_pid}, and no other backend waited "
        f"on it within {WAIT_SECONDS} seconds, so the second insert never met the first."
    )
