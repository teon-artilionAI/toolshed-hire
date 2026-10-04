"""Each write of the admin catalogue as a real transaction on PostgreSQL (FR-22, BR-49).

Every write commits with its audit event or not at all, so a write whose audit
event cannot be written leaves the catalogue exactly as it was, and a write
that commits leaves exactly one event. A change is stamped with the instant of
the clock it was handed. The race for a code, a SKU or a slug is in
tests/integration/test_admin_catalogue_race.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.application.catalogue.admin_commands import (
    CategoryChanges,
    Change,
    EditCategoryCommand,
    EditModelCommand,
    ModelChanges,
    NewCategoryCommand,
    NewModelCommand,
    PublicationCommand,
)
from app.application.catalogue.manage_categories import (
    CreateCategoryUseCase,
    EditCategoryUseCase,
)
from app.application.catalogue.manage_models import CreateModelUseCase, EditModelUseCase
from app.application.catalogue.publish_model import PublishModelUseCase
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.infrastructure.admin_catalogue_query import SqlAdminCatalogue
from app.infrastructure.models import AuditEvent, Category, ProductModel
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking import AuditWriteFailed, UnitOfWorkWithBrokenAudit, opening
from tests.support.catalogue import a_category, a_model
from tests.support.catalogue_terms import model_terms
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

type Write = Callable[[SqlAlchemyUnitOfWork, SqlAdminCatalogue], object]


@pytest.fixture
def reader(postgres_engine: Engine, postgres_session: Session) -> Iterator[Session]:
    """Yield a session of its own, for the read a write answers from.

    It asks for the emptied database first, so it is closed before the tables
    are emptied again, which an open read would otherwise hold up.
    """
    with Session(postgres_engine) as session:
        yield session


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> Actor:
    """Return a committed administrator, as the actor its audit events name."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return Actor(user_id=account.id, role=UserRole.ADMIN)


@pytest.fixture
def stocked(
    postgres_session: Session, postgres_factory: Factory
) -> tuple[Category, ProductModel]:
    """Commit an active category holding one published model."""
    category = a_category(postgres_factory, name="Drilling")
    model = a_model(postgres_factory, name="Hammer", category=category)
    postgres_session.commit()
    return category, model


def run(
    engine: Engine,
    reader: Session,
    write: Write,
    unit_of_work: type[SqlAlchemyUnitOfWork] = SqlAlchemyUnitOfWork,
) -> object:
    """Run one write on a unit of work of its own, answering through `reader`."""
    return write(opening(engine, unit_of_work)(), SqlAdminCatalogue(reader))


def writes(actor: Actor, category_id: UUID, model_id: UUID) -> dict[str, Write]:
    """Return each write of the admin catalogue, bound to a stored category and model."""
    clock = FixedClock()
    return {
        "create a category": lambda uow, read: CreateCategoryUseCase(uow, clock, read).execute(
            NewCategoryCommand(
                actor=actor,
                code="PUMPS",
                name="Pumps",
                slug="pumps",
                description=None,
                parent_category_id=None,
                sort_order=0,
            )
        ),
        "edit a category": lambda uow, read: EditCategoryUseCase(uow, clock, read).execute(
            EditCategoryCommand(
                actor=actor,
                category_id=category_id,
                changes=CategoryChanges(is_active=Change(False)),
            )
        ),
        "create a model": lambda uow, read: CreateModelUseCase(uow, clock, read).execute(
            NewModelCommand(actor=actor, terms=model_terms(category_id))
        ),
        "edit a model": lambda uow, read: EditModelUseCase(uow, clock, read).execute(
            EditModelCommand(
                actor=actor,
                model_id=model_id,
                changes=ModelChanges(daily_rate=Change(Decimal("150.00"))),
            )
        ),
        "hide a model": lambda uow, read: PublishModelUseCase(uow, clock, read).execute(
            PublicationCommand(actor=actor, model_id=model_id, published=False)
        ),
    }


def catalogue_as_stored(session: Session) -> tuple[object, ...]:
    """Return every row of the catalogue and the number of audit events, read afresh."""
    session.expire_all()
    categories = sorted(
        (row.code, row.is_active) for row in session.exec(select(Category)).all()
    )
    models = sorted(
        (row.sku, str(row.daily_rate), row.is_published)
        for row in session.exec(select(ProductModel)).all()
    )
    events = len(session.exec(select(AuditEvent)).all())
    return categories, models, events


WRITE_NAMES: Final[tuple[str, ...]] = (
    "create a category",
    "edit a category",
    "create a model",
    "edit a model",
    "hide a model",
)


class TestEachWriteCommitsWithItsEvent:
    """A write and its audit event commit together, or neither does (BR-49)."""

    @pytest.mark.parametrize("name", WRITE_NAMES)
    def test_a_write_commits_with_one_audit_event(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        reader: Session,
        stocked: tuple[Category, ProductModel],
        administrator: Actor,
        name: str,
    ) -> None:
        category, model = stocked
        _, _, events_before = catalogue_as_stored(postgres_session)
        run(postgres_engine, reader, writes(administrator, category.id, model.id)[name])
        _, _, events_after = catalogue_as_stored(postgres_session)
        assert events_after == events_before + 1

    @pytest.mark.parametrize("name", WRITE_NAMES)
    def test_a_write_whose_audit_event_cannot_be_written_keeps_nothing(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        reader: Session,
        stocked: tuple[Category, ProductModel],
        administrator: Actor,
        name: str,
    ) -> None:
        category, model = stocked
        before = catalogue_as_stored(postgres_session)
        with pytest.raises(AuditWriteFailed):
            run(
                postgres_engine,
                reader,
                writes(administrator, category.id, model.id)[name],
                UnitOfWorkWithBrokenAudit,
            )
        assert catalogue_as_stored(postgres_session) == before

    def test_a_rate_change_is_stamped_with_the_instant_of_the_clock(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        reader: Session,
        stocked: tuple[Category, ProductModel],
        administrator: Actor,
    ) -> None:
        category, model = stocked
        edit_a_model = writes(administrator, category.id, model.id)["edit a model"]
        answer = run(postgres_engine, reader, edit_a_model)
        assert answer.updated_at == DEFAULT_INSTANT
