"""Twenty customers reach for five units at the same moment, through HTTP (NFR-03).

This is the race the whole design exists for, run the way it would really
happen. Twenty drafts of one model for one period at one branch, five
identical units on the shelf, and twenty hold requests sent to the real
application from twenty threads that a barrier releases together. Every
request has a PostgreSQL connection of its own, so the twenty transactions
genuinely overlap.

Exactly five are answered 200 and hold a unit each. The other fifteen are
answered 409 with the problem type `asset-unavailable`. Nobody is answered
500, no unit is held twice and no reservation is left half held.

Two things make that true and both are in play here. The candidate units are
locked with `SELECT ... FOR UPDATE SKIP LOCKED`, so the first five requests
take five different units and the rest find none free. And the exclusion
constraint has the last word, so a request that slips past the lock is refused
by the database and answered with the same clean conflict.

The same race over the allocation function alone, with the row lock bypassed,
is in test_concurrent_allocation.py.
"""

from __future__ import annotations

from collections import Counter
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlmodel import Session, col, select

from app.domain.enums import ReservationStatus, UserRole
from app.infrastructure.models import AssetAllocation, AuditEvent, Reservation, UserAccount
from tests.support.booking_api import (
    FIRST_HIRE,
    RESERVATIONS_PATH,
    BookingClient,
    BookingWorld,
    build_booking_world,
    created,
    hold_path,
)
from tests.support.booking_race import application_on, post_at_once
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 5
CONTENDERS: Final[int] = 20
LOSERS: Final[int] = CONTENDERS - UNITS
PAIR: Final[int] = 2
PAIR_CONTENDERS: Final[int] = 10
CONFLICT_PROBLEM: Final[str] = "asset-unavailable"
DOUBLE_BOOKED_UNITS: Final[str] = (
    "SELECT count(*) FROM asset_allocation a JOIN asset_allocation b "
    "ON a.asset_id = b.asset_id AND a.id < b.id "
    "AND a.released_at IS NULL AND b.released_at IS NULL "
    "AND a.start_date < b.end_date AND b.start_date < a.end_date"
)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch whose shelf holds five identical units."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    postgres_session.commit()
    return built


@pytest.fixture
def customers(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> list[UserAccount]:
    """Return twenty committed customers, each with a profile and a verified address."""
    accounts = [world.customer]
    for _ in range(CONTENDERS - 1):
        account = postgres_factory.user(role=UserRole.CUSTOMER)
        postgres_factory.customer_profile(branch=world.branch, account=account)
        accounts.append(account)
    postgres_session.commit()
    return accounts


def race_for_the_units(
    engine: Engine, world: BookingWorld, customers: list[UserAccount], quantity: int = 1
) -> list[tuple[int, str | None]]:
    """Draft a reservation for every customer, then hold them all at the same moment.

    Returns:
        The status of each hold request, with its problem type when it was refused.

    """
    clock = FixedClock()
    with application_on(engine, clock) as application:
        booking = BookingClient(TestClient(application), clock)
        requests = []
        for customer in customers:
            headers = booking.headers(customer)
            draft = created(
                booking.client.post(
                    RESERVATIONS_PATH,
                    json=world.payload(FIRST_HIRE, quantity=quantity),
                    headers=headers,
                )
            )
            requests.append((hold_path(draft["id"]), headers))
        responses = post_at_once(application, requests)
    return [
        (
            response.status_code,
            None if response.status_code == status.HTTP_200_OK else problem_code(response),
        )
        for response in responses
    ]


class TestTwentyHoldRequestsForFiveUnits:
    """Exactly five succeed, fifteen are refused cleanly, and the database agrees."""

    def test_exactly_five_are_held_and_fifteen_are_answered_409_and_none_500(
        self, postgres_engine: Engine, world: BookingWorld, customers: list[UserAccount]
    ) -> None:
        outcomes = race_for_the_units(postgres_engine, world, customers)

        statuses = Counter(outcome_status for outcome_status, _code in outcomes)
        assert statuses == {status.HTTP_200_OK: UNITS, status.HTTP_409_CONFLICT: LOSERS}, (
            f"Twenty hold requests for five units were answered {dict(statuses)}. Exactly "
            "five must succeed and fifteen must be refused with 409."
        )
        refusals = {code for outcome_status, code in outcomes if code is not None}
        assert refusals == {CONFLICT_PROBLEM}

    def test_the_five_winners_hold_five_different_units_and_nobody_holds_two(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
        customers: list[UserAccount],
    ) -> None:
        asset_ids = {asset.id for asset in world.assets}
        race_for_the_units(postgres_engine, world, customers)

        postgres_session.rollback()
        active = postgres_session.exec(
            select(AssetAllocation).where(col(AssetAllocation.released_at).is_(None))
        ).all()
        assert len(active) == UNITS
        assert {allocation.asset_id for allocation in active} == asset_ids
        assert len({allocation.reservation_line_id for allocation in active}) == UNITS
        assert postgres_session.execute(text(DOUBLE_BOOKED_UNITS)).scalar_one() == 0

    def test_every_reservation_is_either_fully_held_or_still_a_draft(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
        customers: list[UserAccount],
    ) -> None:
        race_for_the_units(postgres_engine, world, customers)

        postgres_session.rollback()
        by_status = Counter(
            reservation.status for reservation in postgres_session.exec(select(Reservation))
        )
        assert by_status == {ReservationStatus.HELD: UNITS, ReservationStatus.DRAFT: LOSERS}
        held_events = postgres_session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "reservation.held")
        ).all()
        assert len(held_events) == UNITS

    def test_ten_requests_for_two_units_each_never_leave_a_reservation_half_held(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        world: BookingWorld,
        customers: list[UserAccount],
    ) -> None:
        """All or nothing under contention (BR-09).

        Five units can serve two pairs at most. How many pairs are served
        depends on how the row locks interleave, because a request that locked
        one unit and found the rest taken is refused and lets its unit go. So
        the number of winners is not pinned. What is pinned is that every
        winner holds both of its units and every loser holds none.
        """
        outcomes = race_for_the_units(
            postgres_engine, world, customers[:PAIR_CONTENDERS], quantity=PAIR
        )

        statuses = Counter(outcome_status for outcome_status, _code in outcomes)
        assert set(statuses) <= {status.HTTP_200_OK, status.HTTP_409_CONFLICT}
        winners = statuses[status.HTTP_200_OK]
        assert winners <= UNITS // PAIR
        postgres_session.rollback()
        active = postgres_session.exec(
            select(AssetAllocation).where(col(AssetAllocation.released_at).is_(None))
        ).all()
        held_per_line = Counter(allocation.reservation_line_id for allocation in active)
        assert set(held_per_line.values()) <= {PAIR}, "A reservation holds one unit of two."
        assert len(held_per_line) == winners
        assert postgres_session.execute(text(DOUBLE_BOOKED_UNITS)).scalar_one() == 0
