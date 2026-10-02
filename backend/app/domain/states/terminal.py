"""The four states a reservation ends in.

A reservation that has been returned, cancelled, marked as not collected or
allowed to expire is finished. `TerminalState` overrides nothing, so every
move is refused by the base class, and the four concrete states only say which
status they are.

Nothing is ever deleted (BR-51). A reservation that ends badly ends here and
stays readable, which is what keeps the reports honest.
"""

from __future__ import annotations

from abc import ABC

from app.domain.enums import ReservationStatus
from app.domain.states.base import ReservationState


class TerminalState(ReservationState, ABC):
    """A finished reservation. It permits no move at all."""


class ReturnedState(TerminalState):
    """Every item is back and the hire is closed."""

    status = ReservationStatus.RETURNED


class CancelledState(TerminalState):
    """Cancelled before collection. Its units were let go."""

    status = ReservationStatus.CANCELLED


class NoShowState(TerminalState):
    """Confirmed and never collected. Its units were let go."""

    status = ReservationStatus.NO_SHOW


class ExpiredState(TerminalState):
    """Held and not confirmed before the hold ran out. Its units were let go."""

    status = ReservationStatus.EXPIRED
