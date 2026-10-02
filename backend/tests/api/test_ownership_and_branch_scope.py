"""Branch scope and the account read again, through HTTP (BR-43).

Counter staff write to their own branch and to no other. One who creates a
reservation at another branch, or holds, confirms or cancels one there, gets
403 with `BranchScopeError`, on the real reservation routes, and nothing is
changed. An administrator and a customer are not scoped by branch, and staff
may read a reservation at any branch.

And an administrator whose role was taken away is refused by the dependency
that reads the account again, even when the session of the request still holds
the old row.

Ownership, which is the other half of who may see what (BR-42), is in
tests/api/test_reservation_reads.py.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import AssetAllocation, Reservation, UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.probe_app import ADMIN_PATH, FRESH_ADMIN_PATH
from tests.support.tokens import authorization_header, mint_access_token

BRANCH_SCOPE_PROBLEM: Final[str] = "branch-scope"
AUTHORISATION_PROBLEM: Final[str] = "authorisation-failure"
SHARED_REQUEST_ID: Final[dict[str, str]] = {
    "X-Request-ID": "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
}


def as_account(account: UserAccount) -> dict[str, str]:
    """Return the request headers of a signed in account, with the shared request id."""
    return {**authorization_header(mint_access_token(account.id)), **SHARED_REQUEST_ID}


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds two units."""
    built = build_booking_world(factory, asset_count=2)
    session.commit()
    return built


@pytest.fixture
def assistant_elsewhere(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant who works at another branch."""
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
    session.commit()
    return assistant


class TestBranchScope:
    """Counter staff write to their own branch and to no other (BR-43)."""

    def test_counter_staff_of_another_branch_cannot_create_a_reservation_here(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant_elsewhere: UserAccount,
    ) -> None:
        response = booking.create(
            assistant_elsewhere, world.payload(customer_profile_id=world.profile.id)
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == BRANCH_SCOPE_PROBLEM
        assert problem_of(response)["errors"] == {"branch_id": str(world.branch.id)}
        assert session.exec(select(Reservation)).all() == []

    @pytest.mark.parametrize("move", ["hold", "confirm", "cancel"])
    def test_counter_staff_of_another_branch_cannot_move_a_reservation_here(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant_elsewhere: UserAccount,
        move: str,
    ) -> None:
        reservation = booking.drafted(world) if move == "hold" else booking.held(world)
        allocations_before = len(session.exec(select(AssetAllocation)).all())

        response = getattr(booking, move)(assistant_elsewhere, reservation["id"])

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == BRANCH_SCOPE_PROBLEM
        unchanged = answered(booking.read(world.customer, reservation["id"]))
        assert unchanged["status"] == reservation["status"]
        assert len(session.exec(select(AssetAllocation)).all()) == allocations_before

    def test_counter_staff_of_another_branch_may_still_read_it(
        self, booking: BookingClient, world: BookingWorld, assistant_elsewhere: UserAccount
    ) -> None:
        held = booking.held(world)
        body = answered(booking.read(assistant_elsewhere, held["id"]))
        assert body["id"] == held["id"]
        assert (body["canHold"], body["canConfirm"], body["canCancel"]) == (False, False, False)

    def test_counter_staff_of_the_branch_may_book_hold_confirm_and_cancel_there(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        draft = created(
            booking.create(assistant, world.payload(customer_profile_id=world.profile.id))
        )
        assert answered(booking.hold(assistant, draft["id"]))["status"] == "HELD"
        assert answered(booking.confirm(assistant, draft["id"]))["status"] == "CONFIRMED"
        assert answered(booking.cancel(assistant, draft["id"]))["status"] == "CANCELLED"

    def test_an_administrator_and_a_customer_are_not_branch_scoped(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        by_admin = created(
            booking.create(administrator, world.payload(customer_profile_id=world.profile.id))
        )
        assert answered(booking.hold(administrator, by_admin["id"]))["status"] == "HELD"
        by_customer = booking.held(world)
        assert by_customer["status"] == "HELD"


class TestTheAccountIsReadAgain:
    """The dependency a sensitive action uses does not trust a row it already holds."""

    @pytest.fixture
    def demoted_behind_the_session(
        self, session: Session, factory: Factory, sqlite_engine: Engine
    ) -> UserAccount:
        """Return an administrator the session still holds as one, demoted in the database.

        The row is changed on a connection of its own, so the copy the session
        has already loaded is left as it was. That is what a request would be
        holding if the role changed after it had authenticated.
        """
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        session.refresh(administrator)
        with sqlite_engine.begin() as connection:
            connection.execute(
                text("UPDATE user_account SET role = :role WHERE email = :email"),
                {"role": UserRole.CUSTOMER.value, "email": administrator.email},
            )
        return administrator

    def test_the_ordinary_chain_admits_on_the_row_the_request_already_holds(
        self, probe_client: TestClient, demoted_behind_the_session: UserAccount
    ) -> None:
        response = probe_client.get(ADMIN_PATH, headers=as_account(demoted_behind_the_session))
        assert response.status_code == status.HTTP_200_OK

    def test_the_fresh_dependency_reads_the_row_again_and_refuses(
        self, probe_client: TestClient, demoted_behind_the_session: UserAccount
    ) -> None:
        response = probe_client.get(
            FRESH_ADMIN_PATH, headers=as_account(demoted_behind_the_session)
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == AUTHORISATION_PROBLEM

    def test_the_fresh_dependency_admits_an_administrator_who_still_is_one(
        self, probe_client: TestClient, session: Session, factory: Factory
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        response = probe_client.get(FRESH_ADMIN_PATH, headers=as_account(administrator))
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == UserRole.ADMIN.value

    def test_the_fresh_dependency_refuses_a_deactivated_administrator(
        self, probe_client: TestClient, session: Session, factory: Factory
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN, is_active=False)
        session.commit()
        response = probe_client.get(FRESH_ADMIN_PATH, headers=as_account(administrator))
        assert response.status_code == status.HTTP_403_FORBIDDEN
