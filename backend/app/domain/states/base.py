"""The base reservation state, which refuses every move (BR-11).

This is the State pattern the design document names. `ReservationState`
declares the seven moves a reservation can be asked to make, and its own
version of each one refuses. A concrete state overrides only the moves that
are legal from it. A move nobody thought about is therefore refused, because
allowing it would have taken somebody writing it.

A refusal is a `StateTransitionError`, which the API answers with HTTP 409.
Its sentence is shown to a customer as it is written, so it says in plain
words where the reservation stands and what could not be done to it.

`UnitAllocator` is the one thing a move needs from outside the domain. Putting
a reservation on hold takes named units (BR-07), and finding and locking those
is the work of a repository. The application layer supplies an allocator, so
the state decides when units are taken and still knows nothing about a
database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, ClassVar, Final, NoReturn, Protocol
from uuid import UUID

from app.domain.enums import ReservationStatus
from app.domain.errors import StateTransitionError

if TYPE_CHECKING:
    from app.domain.availability import AssetAllocation
    from app.domain.booking import Reservation
    from app.domain.booking_line import ReservationLine
    from app.domain.catalogue import ProductModel

# The rule every refused move is logged under.
PERMITTED_TRANSITIONS_RULE: Final[str] = "BR-11"

# Where a reservation stands, as a customer reads it in a refusal.
STANDING_IN_WORDS: Final[Mapping[ReservationStatus, str]] = {
    ReservationStatus.DRAFT: "is still a draft",
    ReservationStatus.HELD: "is on hold",
    ReservationStatus.CONFIRMED: "is confirmed",
    ReservationStatus.COLLECTED: "has been collected",
    ReservationStatus.RETURNED: "has been returned",
    ReservationStatus.CANCELLED: "has been cancelled",
    ReservationStatus.NO_SHOW: "was not collected",
    ReservationStatus.EXPIRED: "has expired",
}
# The names of the moves the application asks a state about.
HOLD_MOVE: Final[str] = "hold"
CONFIRM_MOVE: Final[str] = "confirm"
CANCEL_MOVE: Final[str] = "cancel"
COLLECT_MOVE: Final[str] = "collect"
EXPIRE_MOVE: Final[str] = "expire"
NO_SHOW_MOVE: Final[str] = "mark_no_show"
# What each move would have done, as a customer reads it in a refusal.
PUT_ON_HOLD: Final[str] = "put on hold"
CONFIRMED: Final[str] = "confirmed"
CANCELLED: Final[str] = "cancelled"
COLLECTED: Final[str] = "collected"
EXPIRED: Final[str] = "expired"
MARKED_AS_NOT_COLLECTED: Final[str] = "marked as not collected"
CLOSED: Final[str] = "closed"


def refusal_sentence(status: ReservationStatus, attempted: str) -> str:
    """Return the sentence a move refused from a status is answered with.

    Args:
        status: Where the reservation stands.
        attempted: What the move would have done, in plain words.

    """
    return f"This reservation {STANDING_IN_WORDS[status]}, so it cannot be {attempted}."


class UnitAllocator(Protocol):
    """Holds named units for one line of a reservation (BR-07)."""

    def allocate(
        self, reservation: Reservation, line: ReservationLine
    ) -> Sequence[AssetAllocation]:
        """Hold as many free units as the line asks for, and return the allocations.

        Raises:
            AllocationConflictError: If too few units are free for the period
                at the collection branch.

        """
        ...


class ReservationState:
    """Where a reservation stands, and the moves it may make from there.

    A state holds no data of its own. The reservation carries the data and
    hands itself to the state with each move.
    """

    status: ClassVar[ReservationStatus]

    def permits(self, move: str) -> bool:
        """Return True when this state makes the named move legal.

        A state makes a move legal by overriding it, so the answer is read off
        the class and cannot disagree with what the move would do. The guards
        of the move are still to pass.

        Args:
            move: The name of one of the seven moves, for example `confirm`.

        """
        return getattr(type(self), move) is not getattr(ReservationState, move)

    def hold(
        self,
        reservation: Reservation,
        *,
        now: datetime,
        today: date,
        models: Mapping[UUID, ProductModel],
        allocator: UnitAllocator,
    ) -> None:
        """Refuse to put the reservation on hold."""
        self._reject(ReservationStatus.HELD, PUT_ON_HOLD)

    def confirm(self, reservation: Reservation, *, now: datetime, email_verified: bool) -> None:
        """Refuse to confirm the reservation."""
        self._reject(ReservationStatus.CONFIRMED, CONFIRMED)

    def cancel(
        self,
        reservation: Reservation,
        *,
        now: datetime,
        reason: str | None,
        by_owner_or_staff: bool,
        has_rental: bool,
    ) -> None:
        """Refuse to cancel the reservation."""
        self._reject(ReservationStatus.CANCELLED, CANCELLED)

    def collect(self, reservation: Reservation, *, today: date) -> None:
        """Refuse to record a collection."""
        self._reject(ReservationStatus.COLLECTED, COLLECTED)

    def expire(self, reservation: Reservation, *, now: datetime) -> None:
        """Refuse to lapse the reservation."""
        self._reject(ReservationStatus.EXPIRED, EXPIRED)

    def mark_no_show(
        self, reservation: Reservation, *, now: datetime, branch_closed_at: datetime | None
    ) -> None:
        """Refuse to record that the reservation was never collected."""
        self._reject(ReservationStatus.NO_SHOW, MARKED_AS_NOT_COLLECTED)

    def close(self, reservation: Reservation, *, now: datetime) -> None:
        """Refuse to close the reservation."""
        self._reject(ReservationStatus.RETURNED, CLOSED)

    def _reject(self, target: ReservationStatus, attempted: str) -> NoReturn:
        """Raise the refusal of a move this state does not permit.

        Args:
            target: The status the move would have led to.
            attempted: What the move would have done, in plain words.

        Raises:
            StateTransitionError: Always.

        """
        raise StateTransitionError(
            refusal_sentence(self.status, attempted),
            from_status=self.status.value,
            to_status=target.value,
            rule=PERMITTED_TRANSITIONS_RULE,
        )
