"""Helpers for the tests of the people screens against PostgreSQL itself.

`stock_people` commits a branch, two administrators, a counter assistant and
as many customers with accounts as a test asks for, every tenth of them on
hold, so `user_account` holds far more customers than staff, as it does in
the business, and one walk-in with a name nobody else has.

`plans_of` runs a read and asks the planner how it would run each statement
the read sent, with the very text and parameters the read sent. It does so
inside one transaction in which the tables are analysed and sequential scans
are switched off, and then rolls that transaction back, so the figures never
reach the plans of another test. With sequential scans off a plan still
shows one when no index can serve the statement, which is what the tests look
for.

Importing this module opens no connection.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Engine, event, text
from sqlmodel import Session

from app.domain.enums import AccountStatus, UserRole
from app.infrastructure.models import Branch, UserAccount
from tests.support.factories import Factory

CURSOR_EVENT: Final[str] = "before_cursor_execute"
ANALYSED_TABLES: Final[tuple[str, ...]] = ("user_account", "customer_profile", "branch")
EXPLAIN_PREFIX: Final[str] = "EXPLAIN "
HELD_EVERY: Final[int] = 10
WALKING_THE_TABLE: Final[str] = "Seq Scan"
# A walk-in whose name no other customer shares, which a search can single out.
DISTINCT_NAME: Final[str] = "Thandeka Zungu"

# One statement as the driver was handed it, with its parameters.
type SentStatement = tuple[str, Mapping[str, object] | tuple[object, ...]]


@dataclass(frozen=True, slots=True)
class People:
    """The branch and the staff of a stocked database."""

    branch: Branch
    owner: UserAccount
    bookkeeper: UserAccount
    assistant: UserAccount


def stock_people(session: Session, factory: Factory, customers: int) -> People:
    """Commit a branch, two administrators, an assistant and customers with accounts."""
    branch = factory.branch(code="CBD")
    owner = factory.user(role=UserRole.ADMIN, email="owner@toolshedhire.co.za")
    bookkeeper = factory.user(role=UserRole.ADMIN, email="books@toolshedhire.co.za")
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
    for number in range(customers):
        account = factory.user(role=UserRole.CUSTOMER, email=f"customer{number:04d}@example.co.za")
        profile = factory.customer_profile(branch=branch, account=account)
        profile.display_name = f"Customer {number:04d}"
        if number % HELD_EVERY == 0:
            profile.account_status = AccountStatus.ON_HOLD
        session.add(profile)
    one_of_a_kind = factory.customer_profile(branch=branch)
    one_of_a_kind.display_name = DISTINCT_NAME
    session.add(one_of_a_kind)
    session.commit()
    return People(branch=branch, owner=owner, bookkeeper=bookkeeper, assistant=assistant)


@contextmanager
def sent_statements(engine: Engine) -> Iterator[list[SentStatement]]:
    """Yield a list that fills with every statement and its parameters the engine runs."""
    sent: list[SentStatement] = []

    def _record(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: Mapping[str, object] | tuple[object, ...],
        _context: object,
        _executemany: bool,
    ) -> None:
        """Keep one statement with its parameters."""
        sent.append((statement, parameters))

    event.listen(engine, CURSOR_EVENT, _record)
    try:
        yield sent
    finally:
        event.remove(engine, CURSOR_EVENT, _record)


def plans_of(engine: Engine, read: Callable[[Session], object]) -> list[str]:
    """Return the plan of every statement a read sends, with sequential scans switched off.

    Args:
        engine: The engine of the test database.
        read: Runs the read on the session it is handed.

    """
    with Session(engine) as session:
        for table in ANALYSED_TABLES:
            session.execute(text(f"ANALYZE {table}"))
        session.execute(text("SET LOCAL enable_seqscan = off"))
        with sent_statements(engine) as sent:
            read(session)
        connection = session.connection()
        plans = [
            "\n".join(
                str(row[0])
                for row in connection.exec_driver_sql(EXPLAIN_PREFIX + statement, parameters)
            )
            for statement, parameters in sent
        ]
        session.rollback()
    return plans


__all__ = [
    "DISTINCT_NAME",
    "WALKING_THE_TABLE",
    "People",
    "plans_of",
    "sent_statements",
    "stock_people",
]
