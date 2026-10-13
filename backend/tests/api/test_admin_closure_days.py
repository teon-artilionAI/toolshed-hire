"""The owner's closure days through HTTP.

The owner closes a branch, or every branch, on a day with a reason, and the
branch list a date picker reads shows the day closed at once. A closure is
cancelled and never deleted, and each change keeps an audit event. The list
holds the public holidays once and each live closure with the key it is
cancelled by, and the impact read names the bookings that start or end on the
day so the owner can ring each customer. Only the owner may do any of it.
These run against the in memory database on the still clock's Monday 2 March
2026.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import AuditEvent, ClosureDay, Reservation, UserAccount
from tests.api.role_matrix import NOBODYS_KEY
from tests.support.admin_user_api import actions_about, field_refused, refused_with
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.closure_day_api import (
    CLOSED_DAY_MEMBERS,
    CLOSURE_MEMBERS,
    STOCKTAKE,
    STOCKTAKE_DAY,
    STRANDED_MEMBERS,
    add_closure,
    cancel_closure,
    closure_body,
    list_closed_days,
    read_impact,
)
from tests.support.factories import Factory
from tests.support.http import problem_code

CLOSURE_ENTITY: Final[str] = "closure_day"
HUMAN_RIGHTS_DAY: Final[str] = "2026-03-21"
# A hire collected on the stocktake day and one brought back on it.
COLLECTED_ON_THE_DAY: Final[BookingPeriod] = BookingPeriod(STOCKTAKE_DAY, date(2026, 3, 24))
RETURNED_ON_THE_DAY: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 16), STOCKTAKE_DAY)
AROUND_THE_DAY: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 18), date(2026, 3, 23))


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Commit a branch, a hammer and a customer who can book it."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def owner(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return the committed owner, an administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def added(booking: BookingClient, owner: UserAccount, **members: object) -> dict[str, object]:
    """Close a day at the branch of the body and return the closure, checking the 201."""
    response = add_closure(booking, owner, closure_body(**members))
    assert response.status_code == status.HTTP_201_CREATED, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


class TestAddingAClosure:
    """A closure is kept, recorded and read by the branch list at once."""

    def test_a_closure_of_one_branch_is_answered_recorded_and_closes_the_day(
        self, session: Session, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        closure = added(booking, owner, branch_code=world.branch.code.lower(), reason="  Count ")

        assert set(closure) == CLOSURE_MEMBERS
        assert (closure["branchCode"], closure["day"], closure["reason"]) == (
            world.branch.code,
            STOCKTAKE_DAY.isoformat(),
            "Count",
        )
        assert closure["cancelledAt"] is None
        (event,) = session.exec(
            select(AuditEvent).where(col(AuditEvent.entity_type) == CLOSURE_ENTITY)
        ).all()
        assert event.action == "branch.closure_day_added"
        assert str(event.entity_id) == closure["id"]
        assert event.actor_user_id == owner.id
        assert event.after_state == {
            "branch_code": world.branch.code,
            "day": STOCKTAKE_DAY.isoformat(),
            "reason": "Count",
        }
        branches = answered(booking.client.get("/api/branches"))["items"]
        assert isinstance(branches, list)
        closed = {(day["day"], day["kind"]) for day in branches[0]["closedDays"]}
        assert (STOCKTAKE_DAY.isoformat(), "closure") in closed

    def test_a_closure_of_every_branch_names_no_branch(
        self, session: Session, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        closure = added(booking, owner, branch_code=None, reason="Election day")

        assert closure["branchCode"] is None
        (row,) = session.exec(select(ClosureDay)).all()
        assert (row.branch_id, row.created_by_user_id) == (None, owner.id)

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"day": "2026-03-01"}, "body.day"),
            ({"day": "2027-03-04"}, "body.day"),
            ({"reason": ""}, "body.reason"),
            ({"reason": "   "}, "body.reason"),
            ({"reason": "x" * 121}, "body.reason"),
            ({"branchCode": "NOPE"}, "body.branchCode"),
            ({"note": "Closed"}, "body.note"),
        ],
        ids=["past", "beyond-a-year", "empty", "blank", "long", "unknown-branch", "unknown-member"],
    )
    def test_a_body_that_breaks_a_rule_is_refused_naming_the_field(
        self,
        session: Session,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
        members: dict[str, object],
        field: str,
    ) -> None:
        response = add_closure(booking, owner, closure_body(world.branch.code, **members))

        assert field_refused(response) == [field]
        assert session.exec(select(ClosureDay)).all() == []
        assert actions_about(session, CLOSURE_ENTITY) == []

    def test_a_second_closure_of_the_day_is_a_conflict_in_a_plain_sentence(
        self, session: Session, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        added(booking, owner, branch_code=None, reason="Election day")

        response = add_closure(booking, owner, closure_body(world.branch.code))

        problem = refused_with(response, status.HTTP_409_CONFLICT)
        assert problem["detail"] == (
            "Every branch is already closed on Friday 20 March 2026 (Election day). "
            "Cancel that closure first."
        )
        assert problem_code(response) == "state-transition"
        assert len(session.exec(select(ClosureDay)).all()) == 1


class TestCancellingAClosure:
    """A cancellation opens the day again and keeps the row (BR-51)."""

    def test_a_closure_is_cancelled_kept_and_recorded(
        self, session: Session, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        closure = added(booking, owner, branch_code=world.branch.code)

        cancelled = answered(cancel_closure(booking, owner, closure["id"]))

        assert set(cancelled) == CLOSURE_MEMBERS
        assert cancelled["id"] == closure["id"]
        assert cancelled["cancelledAt"] is not None
        (row,) = session.exec(select(ClosureDay)).all()
        assert row.cancelled_by_user_id == owner.id
        assert actions_about(session, CLOSURE_ENTITY) == [
            "branch.closure_day_added",
            "branch.closure_day_cancelled",
        ]
        listed = answered(list_closed_days(booking, owner, **{"from": STOCKTAKE_DAY.isoformat()}))[
            "items"
        ]
        assert isinstance(listed, list)
        assert all(item["kind"] == "public_holiday" for item in listed)

    def test_a_closure_nobody_added_is_not_found(
        self, booking: BookingClient, owner: UserAccount
    ) -> None:
        response = cancel_closure(booking, owner, NOBODYS_KEY)

        assert problem_code(response) == "not-found"
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_a_closure_cancelled_already_is_a_conflict(
        self, session: Session, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        closure = added(booking, owner, branch_code=world.branch.code)
        answered(cancel_closure(booking, owner, closure["id"]))

        response = cancel_closure(booking, owner, closure["id"])

        problem = refused_with(response, status.HTTP_409_CONFLICT)
        assert problem["detail"] == "This closure was cancelled already."
        assert len(actions_about(session, CLOSURE_ENTITY)) == 2


class TestTheList:
    """The holidays once and each live closure with its key, by day."""

    def test_the_holidays_and_the_closures_are_listed_by_day(
        self, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        closure = added(booking, owner, branch_code=world.branch.code)

        items = answered(list_closed_days(booking, owner))["items"]

        assert isinstance(items, list)
        assert all(set(item) == CLOSED_DAY_MEMBERS for item in items)
        assert items[:2] == [
            {
                "day": STOCKTAKE_DAY.isoformat(),
                "branchCode": world.branch.code,
                "reason": STOCKTAKE,
                "kind": "closure",
                "closureId": closure["id"],
            },
            {
                "day": HUMAN_RIGHTS_DAY,
                "branchCode": None,
                "reason": "Human Rights Day",
                "kind": "public_holiday",
                "closureId": None,
            },
        ]
        assert items[-1]["day"] <= "2027-03-02"
        assert [item["day"] for item in items] == sorted(item["day"] for item in items)

    @pytest.mark.parametrize(
        "params",
        [{"from": "2026-03-10", "to": "2026-03-09"}, {"from": "2026-03-02", "to": "2027-03-03"}],
        ids=["backwards", "longer-than-a-year"],
    )
    def test_a_span_out_of_bounds_is_refused_naming_to(
        self, booking: BookingClient, owner: UserAccount, params: dict[str, object]
    ) -> None:
        assert field_refused(list_closed_days(booking, owner, **params)) == ["query.to"]


class TestTheImpact:
    """The held and confirmed bookings that start or end on the day."""

    def test_the_bookings_starting_or_ending_on_the_day_are_named(
        self,
        session: Session,
        factory: Factory,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
    ) -> None:
        collected = factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            period=COLLECTED_ON_THE_DAY,
        )
        returned = factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            period=RETURNED_ON_THE_DAY,
        )
        returned.status = ReservationStatus.CONFIRMED
        cancelled = factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            period=COLLECTED_ON_THE_DAY,
        )
        cancelled.status = ReservationStatus.CANCELLED
        factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=world.branch,
            period=AROUND_THE_DAY,
        )
        elsewhere = factory.branch()
        factory.reservation(
            profile=world.profile,
            created_by=world.customer,
            branch=elsewhere,
            period=COLLECTED_ON_THE_DAY,
        )
        session.add_all([returned, cancelled])
        session.commit()

        at_branch = answered(
            read_impact(booking, owner, branchCode=world.branch.code, day=STOCKTAKE_DAY.isoformat())
        )
        anywhere = answered(read_impact(booking, owner, day=STOCKTAKE_DAY.isoformat()))

        items = at_branch["items"]
        assert isinstance(items, list)
        assert at_branch["total"] == 2
        assert all(set(item) == STRANDED_MEMBERS for item in items)
        assert [(item["reference"], item["hireDay"]) for item in items] == [
            (returned.reference, "return"),
            (collected.reference, "collection"),
        ]
        assert items[1] == {
            "reference": collected.reference,
            "branchCode": world.branch.code,
            "customerName": world.profile.display_name,
            "customerPhone": world.profile.contact_phone,
            "from": COLLECTED_ON_THE_DAY.start.isoformat(),
            "to": COLLECTED_ON_THE_DAY.end.isoformat(),
            "hireDay": "collection",
        }
        assert anywhere["total"] == 3
        assert session.get(Reservation, collected.id).status is ReservationStatus.HELD

    def test_an_unknown_branch_is_refused_naming_it(
        self, booking: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        response = read_impact(booking, owner, branchCode="NOPE", day=STOCKTAKE_DAY.isoformat())

        assert field_refused(response) == ["query.branchCode"]


class TestOnlyTheOwner:
    """Counter staff and customers are refused every route with 403."""

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_staff_and_customers_are_refused(
        self,
        session: Session,
        factory: Factory,
        booking: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
        role: UserRole,
    ) -> None:
        branch = world.branch if role is UserRole.COUNTER_STAFF else None
        caller = factory.user(role=role, branch=branch)
        session.commit()
        closure = added(booking, owner, branch_code=world.branch.code)

        responses = [
            list_closed_days(booking, caller),
            read_impact(booking, caller, day=STOCKTAKE_DAY.isoformat()),
            add_closure(booking, caller, closure_body(None)),
            cancel_closure(booking, caller, closure["id"]),
        ]

        assert [response.status_code for response in responses] == [
            status.HTTP_403_FORBIDDEN
        ] * len(responses)
        assert actions_about(session, CLOSURE_ENTITY) == ["branch.closure_day_added"]
