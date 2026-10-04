"""A tag two administrators race for, on PostgreSQL (FR-23, BR-34).

A tag is unique, and the use case checks before it writes. A second
administrator can still take the tag between the check and the insert, and
then the unique constraint `asset_asset_tag_key` refuses the row. It is
recognised by its name and answered naming `assetTag`, and the race is staged
for real, with the first insert held open until the second is provably
waiting behind it. Nothing of the losing write is kept.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Final
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.application.catalogue.asset_commands import RegisterUnitCommand
from app.application.catalogue.register_asset import RegisterUnitUseCase
from app.application.refusal import refused_parameter_of
from app.domain.asset_register import registered
from app.domain.enums import UserRole
from app.domain.errors import ValidationFailure
from app.infrastructure.asset_register import SqlAssetRegisterRepository
from app.infrastructure.asset_register_query import SqlAssetRegister
from app.infrastructure.models import UserAccount
from tests.support.booking import opening
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.factories import Factory
from tests.support.race import backend_pid
from tests.support.register_pg import SHELF_TAG as TAG
from tests.support.register_pg import Shelf, new_terms, stock_shelf
from tests.support.register_pg import admin_actor as actor_of

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
def administrator(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


@pytest.fixture
def shelf(postgres_session: Session, postgres_factory: Factory) -> Shelf:
    """Commit a branch, a published hammer and one unit of it on the shelf."""
    return stock_shelf(postgres_session, postgres_factory)


def test_a_tag_two_units_repeat_is_named_by_the_unique_constraint(
    postgres_engine: Engine, shelf: Shelf
) -> None:
    repeat = registered(
        new_terms(TAG),
        unit_id=uuid4(),
        product_model_id=shelf.model.id,
        branch_id=shelf.branch.id,
    )
    with Session(postgres_engine) as session, pytest.raises(DuplicateCatalogueValue) as error:
        SqlAssetRegisterRepository(session).add(repeat, DEFAULT_INSTANT)
    assert error.value.field == "asset_tag"


def test_a_tag_taken_between_the_check_and_the_insert_is_refused_naming_it(
    postgres_engine: Engine, reader: Session, administrator: UserAccount, shelf: Shelf
) -> None:
    with Session(postgres_engine) as holder:
        holder_pid = backend_pid(holder)
        SqlAssetRegisterRepository(holder).add(
            registered(
                new_terms(),
                unit_id=uuid4(),
                product_model_id=shelf.model.id,
                branch_id=shelf.branch.id,
            ),
            DEFAULT_INSTANT,
        )

        def second_administrator() -> object:
            use_case = RegisterUnitUseCase(
                opening(postgres_engine)(), FixedClock(), SqlAssetRegister(reader)
            )
            return use_case.execute(
                RegisterUnitCommand(
                    actor=actor_of(administrator),
                    model_id=shelf.model.id,
                    branch_code="CBD",
                    terms=new_terms(),
                )
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(second_administrator)
            _wait_until_someone_waits_behind(postgres_engine, holder_pid)
            holder.commit()
            with pytest.raises(ValidationFailure) as error:
                pending.result(timeout=WAIT_SECONDS)
    assert (refused_parameter_of(error.value), error.value.message) == (
        "assetTag",
        "Another unit already carries this tag.",
    )
    with Session(postgres_engine) as check:
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
