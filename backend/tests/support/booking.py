"""Wiring for tests that run the booking use cases against a real database.

The API layer wires the use cases for a request. A test of the transaction
itself has no request, so the same wiring is done here, over whichever session
factory the test hands in. The in memory SQLite tests share one session and the
PostgreSQL tests give every unit of work a connection of its own.

`SqlDesk` is the database counterpart of the in memory desk in `memory_world`.
It holds every use case of the booking module, wired the way a request wires
them, and a few helpers that walk a reservation of a `BookingWorld` to the
status a test wants to start from.

The two units of work at the foot of the file are how a test makes a move fail
at a chosen moment, which is the only way to prove that nothing was kept.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Self
from uuid import UUID

from sqlalchemy import Engine
from sqlmodel import Session

from app.application.booking.access import ReservationCommand
from app.application.booking.cancel_reservation import (
    CancelReservationCommand,
    CancelReservationUseCase,
)
from app.application.booking.confirm_reservation import ConfirmReservationUseCase
from app.application.booking.create_reservation import CreateReservationUseCase
from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase
from app.application.booking.hold_reservation import HoldReservationUseCase
from app.application.booking.read_models import ReservationKey
from app.application.booking.read_reservation import ReadReservations
from app.application.booking.reservation_request import (
    CreateReservationCommand,
    RequestedLine,
)
from app.application.booking.views import ReservationView
from app.application.clock import Clock
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.ports import NotificationGateway
from app.application.unit_of_work import UnitOfWork
from app.domain.audit import AuditEvent
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from app.domain.policies import StandardPricingPolicy
from app.infrastructure.models import UserAccount
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking_api import FIRST_HIRE, BookingWorld

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


def actor_of(account: UserAccount) -> Actor:
    """Return an account row as the actor of an operation."""
    return Actor(user_id=account.id, role=account.role, branch_id=account.branch_id)


def customer_of(world: BookingWorld) -> Actor:
    """Return the customer of a world as the actor of an operation.

    Built from the key alone, so it can be called after a commit has expired
    the account row, and from a thread that does not own the session.
    """
    return Actor(user_id=world.customer.id, role=UserRole.CUSTOMER)


def draft_command(
    world: BookingWorld,
    period: BookingPeriod = FIRST_HIRE,
    *,
    quantity: int = DEFAULT_QUANTITY,
    actor: Actor | None = None,
    customer_profile_id: UUID | None = None,
) -> CreateReservationCommand:
    """Return the command that asks for a draft of a world's model at its branch.

    Args:
        world: The rows the draft is made against.
        period: The hire period to book.
        quantity: How many units.
        actor: Who is making the request. The customer themselves when omitted.
        customer_profile_id: The profile staff are booking for.

    """
    return CreateReservationCommand(
        actor=actor or customer_of(world),
        branch_code=world.branch.code,
        start=period.start,
        end=period.end,
        lines=(RequestedLine(model_slug=world.product_model.slug, quantity=quantity),),
        customer_profile_id=customer_profile_id,
    )


@dataclass(frozen=True, slots=True)
class SqlDesk:
    """Every use case of the booking module, wired over real units of work."""

    create: CreateReservationUseCase
    hold: HoldReservationUseCase
    confirm: ConfirmReservationUseCase
    cancel: CancelReservationUseCase
    reads: ReadReservations
    sweep: ExpireHoldsAndNoShowsUseCase

    def drafted(self, command: CreateReservationCommand) -> ReservationView:
        """Create a draft and return it."""
        return self.create.execute(command)

    def held(self, command: CreateReservationCommand) -> ReservationView:
        """Create a draft, put it on hold as the same actor and return it."""
        draft = self.create.execute(command)
        return self.hold.execute(move_on(draft, command.actor))

    def confirmed(self, command: CreateReservationCommand) -> ReservationView:
        """Create a draft, hold it, confirm it as the same actor and return it."""
        held = self.held(command)
        return self.confirm.execute(move_on(held, command.actor))


def move_on(view: ReservationView, actor: Actor) -> ReservationCommand:
    """Return the command that names a reservation for its next move."""
    return ReservationCommand(actor=actor, key=ReservationKey.of(view.detail.id))


def cancellation_of(
    view: ReservationView, actor: Actor, reason: str | None = None
) -> CancelReservationCommand:
    """Return the command that cancels a reservation."""
    return CancelReservationCommand(
        actor=actor, key=ReservationKey.of(view.detail.id), reason=reason
    )


def sql_desk(
    unit_of_work: Callable[[], UnitOfWork], gateway: NotificationGateway, clock: Clock
) -> SqlDesk:
    """Return the booking use cases wired the way a request wires them.

    Args:
        unit_of_work: Builds a unit of work. Called once for each use case and
            once for the dispatcher, so no two of them share an open
            transaction.
        gateway: The email gateway.
        clock: The clock.

    """
    sweep = ExpireHoldsAndNoShowsUseCase(unit_of_work(), clock)
    dispatcher = NotificationDispatcher(unit_of_work(), gateway, clock)
    return SqlDesk(
        create=CreateReservationUseCase(unit_of_work(), clock, StandardPricingPolicy()),
        hold=HoldReservationUseCase(unit_of_work(), clock, sweep),
        confirm=ConfirmReservationUseCase(unit_of_work(), clock, sweep, dispatcher),
        cancel=CancelReservationUseCase(unit_of_work(), clock),
        reads=ReadReservations(unit_of_work(), clock, sweep),
        sweep=sweep,
    )


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
    "SqlDesk",
    "UnitOfWorkThatCannotCommit",
    "UnitOfWorkWithBrokenAudit",
    "actor_of",
    "borrowing",
    "cancellation_of",
    "customer_of",
    "draft_command",
    "move_on",
    "opening",
    "sql_desk",
]
