"""A booking belongs to a customer profile, not to a sign in account.

The request and the token both name an account, because that is what a signed
in caller has. The reservation is owned by that account's customer profile, so
that a walk-in with no login can own a booking history on the same terms. The
use case resolves one into the other, and these tests pin both halves of that:
the right profile is recorded, and an account with no profile cannot own a
booking at all.

These run against the in memory database, like the rest of tests/api.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import Reservation, ReservationLine
from tests.support.factories import Factory
from tests.support.http import booking_payload, future_period, problem_code, problem_of
from tests.support.scenarios import AllocationScenario, build_allocation_scenario
from tests.support.tokens import authorization_header, mint_access_token

ALLOCATIONS_PATH: Final[str] = "/api/allocations"
NOT_FOUND_PROBLEM: Final[str] = "not-found"


def payload_for(scenario: AllocationScenario) -> dict[str, object]:
    """Return the booking body for a scenario's product model and branch."""
    return booking_payload(
        product_model_id=scenario.product_model.id,
        branch_id=scenario.branch.id,
        period=future_period(),
    )


def stored_reservation(session: Session, response_body: dict[str, object]) -> Reservation:
    """Return the reservation row a 201 response describes."""
    reservation = session.get(Reservation, UUID(str(response_body["reservationId"])))
    assert reservation is not None, "The API reported a reservation that is not in the database."
    return reservation


class TestTheReservationIsOwnedByTheCustomersProfile:
    """The account is how the caller is named. The profile is what owns the booking."""

    def test_a_customer_booking_is_recorded_against_their_own_profile(
        self, client: TestClient, session: Session, factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(factory, future_period())
        session.commit()
        response = client.post(
            ALLOCATIONS_PATH,
            json=payload_for(scenario),
            headers=authorization_header(mint_access_token(scenario.customer.id)),
        )
        assert response.status_code == status.HTTP_201_CREATED
        reservation = stored_reservation(session, response.json())
        assert reservation.customer_profile_id == scenario.profile.id
        assert reservation.created_by_user_id == scenario.customer.id

    def test_counter_staff_booking_for_a_customer_is_recorded_against_that_customers_profile(
        self, client: TestClient, session: Session, factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(factory, future_period())
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=scenario.branch)
        session.commit()
        payload = payload_for(scenario)
        payload["customerUserId"] = str(scenario.customer.id)
        response = client.post(
            ALLOCATIONS_PATH,
            json=payload,
            headers=authorization_header(mint_access_token(assistant.id)),
        )
        assert response.status_code == status.HTTP_201_CREATED
        reservation = stored_reservation(session, response.json())
        assert reservation.customer_profile_id == scenario.profile.id
        assert reservation.created_by_user_id == assistant.id

    def test_the_line_snapshots_every_price_on_the_product_model(
        self, client: TestClient, session: Session, factory: Factory
    ) -> None:
        """BR-20. A later catalogue price change must not rewrite this booking."""
        scenario = build_allocation_scenario(factory, future_period())
        session.commit()
        response = client.post(
            ALLOCATIONS_PATH,
            json=payload_for(scenario),
            headers=authorization_header(mint_access_token(scenario.customer.id)),
        )
        assert response.status_code == status.HTTP_201_CREATED
        line = session.get(ReservationLine, UUID(response.json()["reservationLineId"]))
        assert line is not None
        model = scenario.product_model
        assert line.daily_rate_snapshot == model.daily_rate
        assert line.weekly_rate_snapshot == model.weekly_rate
        assert line.deposit_snapshot == model.deposit_amount
        assert line.late_fee_per_day_snapshot == model.late_fee_per_day
        assert line.replacement_value_snapshot == model.replacement_value


class TestAnAccountWithNoProfileCannotOwnABooking:
    """Staff accounts carry no customer profile, so they cannot be the customer."""

    def test_a_booking_for_an_account_with_no_customer_profile_is_refused_with_404(
        self, client: TestClient, session: Session, factory: Factory
    ) -> None:
        """An administrator who names no customer is booking for their own account."""
        scenario = build_allocation_scenario(factory, future_period())
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        response = client.post(
            ALLOCATIONS_PATH,
            json=payload_for(scenario),
            headers=authorization_header(mint_access_token(administrator.id)),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM
        assert problem_of(response)["errors"] == {"customer_user_id": str(administrator.id)}

    def test_a_refused_booking_leaves_no_reservation_behind(
        self, client: TestClient, session: Session, factory: Factory
    ) -> None:
        scenario = build_allocation_scenario(factory, future_period())
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        client.post(
            ALLOCATIONS_PATH,
            json=payload_for(scenario),
            headers=authorization_header(mint_access_token(administrator.id)),
        )
        # The scenario builds exactly one reservation of its own.
        remaining = session.exec(select(Reservation)).all()
        assert [reservation.id for reservation in remaining] == [scenario.reservation.id]
