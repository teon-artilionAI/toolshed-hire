"""The reservation states, which are the rules of the booking lifecycle (BR-11).

There are eight. Four can still move, which are DRAFT, HELD, CONFIRMED and
COLLECTED, and four are where a reservation ends, which are RETURNED,
CANCELLED, NO_SHOW and EXPIRED. A reservation hands every move to the state it
is in, and `state_for` is how it finds that state from its status.

A state carries no data, so one instance of each serves every reservation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from app.domain.enums import ReservationStatus
from app.domain.states.active import CollectedState, ConfirmedState, DraftState, HeldState
from app.domain.states.base import ReservationState, UnitAllocator
from app.domain.states.guards import HOLD_DURATION, LATE_CANCELLATION_CUTOFF
from app.domain.states.terminal import (
    CancelledState,
    ExpiredState,
    NoShowState,
    ReturnedState,
    TerminalState,
)

__all__ = [
    "HOLD_DURATION",
    "LATE_CANCELLATION_CUTOFF",
    "CancelledState",
    "CollectedState",
    "ConfirmedState",
    "DraftState",
    "ExpiredState",
    "HeldState",
    "NoShowState",
    "ReservationState",
    "ReturnedState",
    "TerminalState",
    "UnitAllocator",
    "state_for",
]

# Explicit and total. A status added to the enumeration without a state here
# fails the first time a reservation in it is asked to move.
_STATES: Final[Mapping[ReservationStatus, ReservationState]] = {
    state.status: state
    for state in (
        DraftState(),
        HeldState(),
        ConfirmedState(),
        CollectedState(),
        ReturnedState(),
        CancelledState(),
        NoShowState(),
        ExpiredState(),
    )
}


def state_for(status: ReservationStatus) -> ReservationState:
    """Return the state that stands for a status.

    Raises:
        KeyError: If a status has been added without a state. This is
            deliberate. A fallback would let a reservation move by a rule
            nobody wrote.

    """
    return _STATES[status]
