"""Wiring for tests that run the reservation use case against a real database.

The API layer wires the use case for a request. A test of the transaction
itself has no request, so the same wiring is done here, over whichever session
factory the test hands in. The in memory SQLite tests share one session and the
PostgreSQL tests give the unit of work a connection of its own.

The two units of work at the foot of the file are how a test makes a booking
fail at a chosen moment, which is the only way to prove that nothing was kept.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, Self

from sqlalchemy import Engine
from sqlmodel import Session

from app.application.booking.create_reservation import (
    CreateReservationCommand,
    CreateReservationUseCase,
)
from app.application.clock import Clock
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.ports import NotificationGateway
from app.application.unit_of_work import UnitOfWork
from app.domain.audit import AuditEvent
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.scenarios import AllocationScenario

DEFAULT_QUANTITY: Final[int] = 1


class AuditWriteFailed(RuntimeError):
    """Raised in place of an audit write, to stand for an audit store that is down."""


class _BrokenAuditLog:
    """An audit log that cannot be written to."""

    def record(self, event: AuditEvent) -> None:
        """Fail every write."""
        raise AuditWriteFailed(
            f"The audit event {event.action!r} could not be written, because this test "
            "switched the audit log off."
        )


class UnitOfWorkWithBrokenAudit(SqlAlchemyUnitOfWork):
    """The real SQL unit of work, except that its audit log always fails."""

    def __enter__(self) -> Self:
        """Open the real transaction, then replace the audit log with the broken one."""
        entered = super().__enter__()
        self.audit = _BrokenAuditLog()
        return entered


class CommitFailed(RuntimeError):
    """Raised in place of a commit, to stand for a connection lost at the last moment."""


class UnitOfWorkThatCannotCommit(SqlAlchemyUnitOfWork):
    """The real SQL unit of work, except that the commit never succeeds.

    Everything the use case writes reaches the database inside the open
    transaction, the queued notification included. What the test then looks at
    is how much of it survived the commit that did not happen.
    """

    def commit(self) -> None:
        """Fail instead of committing."""
        raise CommitFailed("The commit failed, because this test made it fail.")


def command_for(
    scenario: AllocationScenario,
    period: BookingPeriod,
    *,
    actor: Actor | None = None,
    quantity: int = DEFAULT_QUANTITY,
) -> CreateReservationCommand:
    """Return the command that books a scenario's product model for its customer.

    Args:
        scenario: The rows the booking is made against.
        period: The hire period to book.
        actor: Who is making the request. The customer themselves when omitted.
        quantity: How many units.

    """
    return CreateReservationCommand(
        actor=actor or Actor(user_id=scenario.customer.id, role=UserRole.CUSTOMER),
        customer_user_id=scenario.customer.id,
        branch_id=scenario.branch.id,
        product_model_id=scenario.product_model.id,
        period=period,
        quantity=quantity,
    )


def sql_use_case(
    unit_of_work: Callable[[], UnitOfWork], gateway: NotificationGateway, clock: Clock
) -> CreateReservationUseCase:
    """Return the reservation use case wired the way a request wires it.

    Args:
        unit_of_work: Builds a unit of work. Called twice, once for the use
            case and once for its dispatcher, so the two never share an open
            transaction.
        gateway: The email gateway.
        clock: The clock.

    """
    dispatcher = NotificationDispatcher(unit_of_work(), gateway, clock)
    return CreateReservationUseCase(unit_of_work(), clock, dispatcher)


def borrowing(session: Session) -> Callable[[], SqlAlchemyUnitOfWork]:
    """Return a factory of units of work that borrow one open session.

    This is what a request does with its request scoped session. The unit of
    work does not close it.
    """
    return lambda: SqlAlchemyUnitOfWork(lambda: session, close_on_exit=False)


def opening(
    engine: Engine, unit_of_work: type[SqlAlchemyUnitOfWork] = SqlAlchemyUnitOfWork
) -> Callable[[], SqlAlchemyUnitOfWork]:
    """Return a factory of units of work that each open a session of their own.

    This is what a test of real transactions wants. The use case works on its
    own connection, and the test looks at the result through a different one.

    Args:
        engine: The engine each session is opened on.
        unit_of_work: The class to build, for a test that needs one that fails.

    """
    return lambda: unit_of_work(lambda: Session(engine))


__all__ = [
    "AuditWriteFailed",
    "CommitFailed",
    "UnitOfWorkThatCannotCommit",
    "UnitOfWorkWithBrokenAudit",
    "borrowing",
    "command_for",
    "opening",
    "sql_use_case",
]
