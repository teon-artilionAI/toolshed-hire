"""Releasing one unit of a booking by hand, and giving a short booking replacements (US-32).

The force release is the manual escape hatch of the office, for the rare unit
that the record says is held for a booking when it cannot be handed over, a
unit still out with another customer for example. An administrator releases
the one allocation with the reason REALLOCATED, and the booking then holds
fewer units than it asks for. An allocation already released is refused, and
so is a unit out on hire on this booking, which is let go when it comes back.

A booking that is short is given replacement units through the same allocation
path a hold uses (BR-07, BR-09). Every short line is topped up in one go, and
a line that cannot be given all it is short of fails the whole reallocation,
so a booking is never left half topped up. Only a booking on hold or confirmed
can be topped up, because only those still wait for their units.

A short booking cannot be confirmed (BR-08) or collected, and how many units it
is short of is what `units_short_of` answers and `units_missing_message` says.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.errors import StateTransitionError
from app.domain.states.base import UnitAllocator, refusal_sentence
from app.domain.states.guards import ensure_every_unit_is_held

FORCE_RELEASE_RULE: Final[str] = "BR-44"
REALLOCATION_RULE: Final[str] = "BR-09"
ONE_UNIT: Final[int] = 1
# The bookings that still wait for their units, and so can be topped up.
WAITING_FOR_UNITS: Final[frozenset[ReservationStatus]] = frozenset(
    {ReservationStatus.HELD, ReservationStatus.CONFIRMED}
)
GIVEN_REPLACEMENTS: Final[str] = "given replacement units"

ALREADY_RELEASED_MESSAGE: Final[str] = (
    "This unit is no longer held for the booking, so there is nothing to release."
)
ON_HIRE_MESSAGE: Final[str] = (
    "This unit is out on hire on this booking, so it cannot be released. It is let go when "
    "it comes back."
)


def units_short_of(reservation: Reservation) -> int:
    """Return how many units the lines of a reservation still need, in all."""
    return sum(line.shortfall() for line in reservation.lines)


def units_missing_message(count: int) -> str:
    """Return the sentence that says how many units a booking is short of."""
    if count == ONE_UNIT:
        return (
            "One unit of this booking is missing. Allocate a replacement before the "
            "equipment is handed over."
        )
    return (
        f"{count} units of this booking are missing. Allocate replacements before the "
        "equipment is handed over."
    )


def force_release(reservation: Reservation, allocation_id: UUID, now: datetime) -> AssetAllocation:
    """Release one allocation of a locked reservation with the reason REALLOCATED.

    Args:
        reservation: The reservation that holds the unit, locked by the caller.
        allocation_id: The allocation to release.
        now: The current instant, from the clock.

    Returns:
        The allocation, released.

    Raises:
        LookupError: If the reservation does not hold the allocation, which
            means the caller locked the wrong reservation for it.
        StateTransitionError: If the allocation was already released, or its
            unit is out on hire on this booking.

    """
    allocation = next(
        (
            held
            for line in reservation.lines
            for held in line.allocations
            if held.id == allocation_id
        ),
        None,
    )
    if allocation is None:
        raise LookupError(
            f"Attempted to release allocation {allocation_id} through reservation "
            f"{reservation.reference}, which does not hold it."
        )
    if not allocation.is_active():
        raise _refused(reservation, ALREADY_RELEASED_MESSAGE, FORCE_RELEASE_RULE)
    if reservation.status is ReservationStatus.COLLECTED:
        raise _refused(reservation, ON_HIRE_MESSAGE, FORCE_RELEASE_RULE)
    allocation.release(ReleaseReason.REALLOCATED, now)
    return allocation


def give_replacement_units(
    reservation: Reservation, allocator: UnitAllocator
) -> list[AssetAllocation]:
    """Top up every short line of a reservation on hold or confirmed, all or nothing.

    Args:
        reservation: The reservation, locked by the caller.
        allocator: Takes free units for a line through the allocation path.

    Returns:
        The allocations taken, none when no line was short.

    Raises:
        StateTransitionError: If the reservation is neither on hold nor
            confirmed.
        AllocationConflictError: If a line could not be given every unit it
            is short of. Nothing is attached to the reservation then.

    """
    if reservation.status not in WAITING_FOR_UNITS:
        raise _refused(
            reservation, refusal_sentence(reservation.status, GIVEN_REPLACEMENTS), REALLOCATION_RULE
        )
    short = [line for line in reservation.lines if line.shortfall()]
    taken = {line.id: list(allocator.allocate(reservation, line)) for line in short}
    ensure_every_unit_is_held(reservation, taken)
    for line in short:
        line.allocations.extend(taken[line.id])
    return [allocation for allocations in taken.values() for allocation in allocations]


def _refused(reservation: Reservation, message: str, rule: str) -> StateTransitionError:
    """Return the refusal of a move on the units of a reservation."""
    return StateTransitionError(
        message,
        from_status=reservation.status.value,
        to_status=reservation.status.value,
        rule=rule,
    )
