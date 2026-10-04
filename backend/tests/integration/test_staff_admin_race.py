"""Two administrators changing each other at the same moment, on PostgreSQL (US-35).

Every change to a staff account locks every active administrator first, in
the order of their keys. Two changes at once therefore take turns, and the
second is answered from what the first committed. The races here are staged
for real. The first change is held at its commit until PostgreSQL reports the
second waiting behind it, and only then let go.

Two administrators who demote each other at once leave one administrator, and
the second is refused because it is no longer one. Two administrators who
each step down at once leave one administrator as well, and the second is
refused by the rule about the last one, which is asked under the lock and so
sees the first step down. Without the lock both would have read two
administrators, both changes would have gone through and none would be left.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Final

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.application.catalogue.admin_commands import Change
from app.application.identity.staff_commands import EditStaffAccountCommand, StaffChanges
from app.application.identity.staff_edit import EditStaffAccountUseCase
from app.domain.enums import UserRole
from app.domain.errors import AuthorisationFailure, StateTransitionError
from app.domain.identity import Actor
from app.domain.staff_account import LAST_ADMINISTRATOR_MESSAGE
from app.infrastructure.models import Branch, UserAccount
from app.infrastructure.staff_query import SqlStaffDirectory
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.no_show_pg import (
    UnitOfWorkThatAnnouncesItsBackend,
    UnitOfWorkThatPausesAtCommit,
)
from tests.support.race import (
    BARRIER_TIMEOUT_SECONDS,
    BLOCKED_POLL_SECONDS,
    RESULT_TIMEOUT_SECONDS,
    wait_until_backend_is_blocked,
)

pytestmark = pytest.mark.postgres

ACTIVE_ADMINISTRATORS: Final[str] = (
    "SELECT count(*) FROM user_account WHERE role = 'ADMIN' AND is_active"
)
UPDATES_RECORDED: Final[str] = (
    "SELECT count(*) FROM audit_event WHERE action = 'user_account.updated'"
)


@dataclass
class Staging:
    """The signals between the change held at its commit and the one that waits behind it."""

    about_to_commit: threading.Event = field(default_factory=threading.Event)
    may_commit: threading.Event = field(default_factory=threading.Event)
    backends: list[int] = field(default_factory=list)

    def held(self, engine: Engine) -> SqlAlchemyUnitOfWork:
        """Return a unit of work that announces its commit and waits to be let go."""
        unit_of_work = UnitOfWorkThatPausesAtCommit(lambda: Session(engine))
        unit_of_work.about_to_commit = self.about_to_commit
        unit_of_work.may_commit = self.may_commit
        return unit_of_work

    def waiting(self, engine: Engine) -> SqlAlchemyUnitOfWork:
        """Return a unit of work that writes down the backend of its transaction."""
        unit_of_work = UnitOfWorkThatAnnouncesItsBackend(lambda: Session(engine))
        unit_of_work.backends = self.backends
        return unit_of_work


@pytest.fixture
def reader(postgres_engine: Engine, postgres_session: Session) -> Iterator[Session]:
    """Yield a session of its own for the answers, closed before the tables are emptied."""
    with Session(postgres_engine) as session:
        yield session


@pytest.fixture
def branch(postgres_session: Session, postgres_factory: Factory) -> Branch:
    """Commit the CBD branch."""
    made = postgres_factory.branch(code="CBD")
    postgres_session.commit()
    return made


@pytest.fixture
def administrators(
    postgres_session: Session, postgres_factory: Factory, branch: Branch
) -> tuple[UserAccount, UserAccount]:
    """Commit the owner and the bookkeeper, the only two administrators."""
    owner = postgres_factory.user(role=UserRole.ADMIN)
    bookkeeper = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return owner, bookkeeper


def demotion(
    unit_of_work: SqlAlchemyUnitOfWork,
    reader: Session,
    *,
    actor: UserAccount,
    target: UserAccount,
    branch: Branch,
) -> Callable[[], object]:
    """Return a call in which `actor` moves `target` to the counter at a branch."""
    command = EditStaffAccountCommand(
        actor=Actor(user_id=actor.id, role=UserRole.ADMIN),
        user_id=target.id,
        changes=StaffChanges(role=Change(UserRole.COUNTER_STAFF), branch_code=Change(branch.code)),
    )
    use_case = EditStaffAccountUseCase(unit_of_work, FixedClock(), SqlStaffDirectory(reader))
    return lambda: use_case.execute(command)


def run_staged(
    engine: Engine, staging: Staging, first: Callable[[], object], second: Callable[[], object]
) -> tuple[BaseException | None, BaseException | None]:
    """Hold the first change at its commit, let it go once the second waits, and return both ends.

    Returns:
        What each change raised, or None when it committed.

    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        held = pool.submit(first)
        assert staging.about_to_commit.wait(timeout=BARRIER_TIMEOUT_SECONDS), (
            "The first change never reached its commit, so there was nothing to race."
        )
        waiting = pool.submit(second)
        _wait_until_opened(staging.backends)
        with Session(engine) as watcher:
            wait_until_backend_is_blocked(watcher, staging.backends[0])
        staging.may_commit.set()
        return (
            held.exception(timeout=RESULT_TIMEOUT_SECONDS),
            waiting.exception(timeout=RESULT_TIMEOUT_SECONDS),
        )


def _wait_until_opened(backends: list[int]) -> None:
    """Block until the second change has opened its transaction and noted its backend."""
    deadline = time.monotonic() + BARRIER_TIMEOUT_SECONDS
    while not backends and time.monotonic() < deadline:
        time.sleep(BLOCKED_POLL_SECONDS)
    assert backends, "The second change never opened its transaction."


def count_of(engine: Engine, statement: str) -> int:
    """Return one count, read on a connection of its own."""
    with engine.connect() as connection:
        return int(connection.execute(text(statement)).scalar_one())


def test_two_administrators_demoting_each_other_leave_one(
    postgres_engine: Engine,
    reader: Session,
    branch: Branch,
    administrators: tuple[UserAccount, UserAccount],
) -> None:
    owner, bookkeeper = administrators
    staging = Staging()
    first = demotion(
        staging.held(postgres_engine), reader, actor=owner, target=bookkeeper, branch=branch
    )
    second = demotion(
        staging.waiting(postgres_engine), reader, actor=bookkeeper, target=owner, branch=branch
    )
    first_error, second_error = run_staged(postgres_engine, staging, first, second)
    assert first_error is None
    assert isinstance(second_error, AuthorisationFailure)
    assert count_of(postgres_engine, ACTIVE_ADMINISTRATORS) == 1
    assert count_of(postgres_engine, UPDATES_RECORDED) == 1


def test_two_administrators_stepping_down_at_once_leave_one(
    postgres_engine: Engine,
    reader: Session,
    branch: Branch,
    administrators: tuple[UserAccount, UserAccount],
) -> None:
    owner, bookkeeper = administrators
    staging = Staging()
    first = demotion(
        staging.held(postgres_engine), reader, actor=owner, target=owner, branch=branch
    )
    second = demotion(
        staging.waiting(postgres_engine),
        reader,
        actor=bookkeeper,
        target=bookkeeper,
        branch=branch,
    )
    first_error, second_error = run_staged(postgres_engine, staging, first, second)
    assert first_error is None
    assert isinstance(second_error, StateTransitionError)
    assert second_error.message == LAST_ADMINISTRATOR_MESSAGE
    assert count_of(postgres_engine, ACTIVE_ADMINISTRATORS) == 1
    assert count_of(postgres_engine, UPDATES_RECORDED) == 1
