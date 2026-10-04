"""The audit log through HTTP, and every refusal of it (FR-26, BR-49).

A customer books, holds and confirms, which writes three events with the
customer as the actor. The administrator reads them newest first, narrows them
by the record, the action, the account and the days, and pages through them.
A hold the sweep lapses writes an event with no actor. These run against the
in memory database, and the clock stands still on Monday the second of March
2026 at ten in the morning in Cape Town.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.admin_api import (
    AUDIT_EVENT_MEMBERS,
    AUDIT_EVENTS_PATH,
    PAGE_MEMBERS,
    read_audit,
)
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.report_api import refused_fields

TODAY: Final[str] = "2026-03-02"
TOMORROW: Final[str] = "2026-03-03"
REQUEST_ID: Final[str] = "6f1f6a39-5b0c-4d4e-8a52-0d6f5b8d2c11"
PAST_THE_HOLD: Final[timedelta] = timedelta(minutes=31)
LIFECYCLE: Final[list[str]] = [
    "reservation.confirmed",
    "reservation.held",
    "reservation.created",
]


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world with one unit."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def actions(page: dict[str, object]) -> list[str]:
    """Return the actions of the events on a page, in the order the page lists them."""
    items = page["items"]
    assert isinstance(items, list)
    return [str(item["action"]) for item in items]


class TestTheLog:
    """Newest first, with who acted and what changed."""

    def test_the_events_of_a_booking_are_listed_newest_first_with_the_actor(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        confirmed = booking.confirmed(world)
        page = answered(read_audit(booking, administrator))

        assert page.keys() == PAGE_MEMBERS
        assert (page["page"], page["pageSize"], page["total"]) == (1, 20, 3)
        assert actions(page) == LIFECYCLE
        newest, _held, created = page["items"]
        assert newest.keys() == AUDIT_EVENT_MEMBERS
        assert (newest["actorUserId"], newest["actorName"], newest["actorRole"]) == (
            str(world.customer.id), world.customer.full_name, "CUSTOMER"
        )
        assert (newest["entityType"], newest["entityId"]) == ("reservation", confirmed["id"])
        assert newest["occurredAt"] == "2026-03-02T10:00:00+02:00"
        assert newest["afterState"]["status"] == "CONFIRMED"
        assert newest["beforeState"]["status"] == "HELD"
        assert created["beforeState"] == {}
        assert newest["id"] > created["id"]

    def test_an_event_keeps_the_id_of_the_request_that_wrote_it(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        draft = booking.drafted(world)
        answered(booking.hold(world.customer, draft["id"], request_id=REQUEST_ID))
        page = answered(read_audit(booking, administrator, action="reservation.held"))
        (held,) = page["items"]
        assert held["requestId"] == REQUEST_ID

    def test_an_event_the_sweep_wrote_has_no_actor(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        held = booking.held(world)
        booking.clock.advance(PAST_THE_HOLD)
        answered(booking.read(world.customer, held["id"]))
        page = answered(read_audit(booking, administrator, action="reservation.expired"))
        (lapsed,) = page["items"]
        assert (lapsed["actorUserId"], lapsed["actorName"], lapsed["actorRole"]) == (
            None, None, None
        )


class TestTheFilters:
    """Each filter narrows the log, and the pages divide it."""

    def test_the_log_is_narrowed_by_the_record(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        first = booking.confirmed(world)
        booking.drafted(world)
        by_record = answered(
            read_audit(booking, administrator, entityType="reservation", entityId=first["id"])
        )
        assert actions(by_record) == LIFECYCLE
        by_key = answered(read_audit(booking, administrator, entityId=first["id"]))
        assert by_key["total"] == 3
        by_kind = answered(read_audit(booking, administrator, entityType="reservation"))
        assert by_kind["total"] == 4

    def test_the_log_is_narrowed_by_the_action_and_by_the_account(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        booking.confirmed(world)
        assert actions(answered(read_audit(booking, administrator, action="reservation.held"))) == [
            "reservation.held"
        ]
        mine = answered(read_audit(booking, administrator, actorUserId=str(world.customer.id)))
        assert mine["total"] == 3
        theirs = answered(read_audit(booking, administrator, actorUserId=str(administrator.id)))
        assert theirs["total"] == 0

    def test_the_log_is_narrowed_by_days_and_both_days_are_included(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        booking.confirmed(world)
        today = answered(read_audit(booking, administrator, **{"from": TODAY, "to": TODAY}))
        assert today["total"] == 3
        later = answered(read_audit(booking, administrator, **{"from": TOMORROW}))
        assert later["total"] == 0
        before = answered(read_audit(booking, administrator, to="2026-03-01"))
        assert before["total"] == 0

    def test_a_page_holds_what_it_is_asked_to(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        booking.confirmed(world)
        second = answered(read_audit(booking, administrator, page=2, pageSize=1))
        assert (second["page"], second["pageSize"], second["total"]) == (2, 1, 3)
        assert actions(second) == ["reservation.held"]


class TestTheRefusals:
    """A refused parameter is named, and only an administrator may read the log."""

    def test_a_span_that_ends_before_it_begins_is_refused_naming_to(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        refused = read_audit(booking, administrator, **{"from": TOMORROW, "to": TODAY})
        assert refused_fields(refused) == {"query.to"}
        assert refused.json()["errors"]["fields"]["query.to"] == (
            "The last day has to be on or after the first day."
        )

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"entityId": "not-a-key"}, "query.entityId"),
            ({"actorUserId": "not-a-key"}, "query.actorUserId"),
            ({"from": "yesterday"}, "query.from"),
            ({"page": 0}, "query.page"),
            ({"pageSize": 101}, "query.pageSize"),
            ({"pageSize": 0}, "query.pageSize"),
            ({"entityType": "x" * 41}, "query.entityType"),
            ({"action": "x" * 61}, "query.action"),
        ],
    )
    def test_a_value_that_cannot_be_read_is_refused_naming_it(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        params: dict[str, object],
        field: str,
    ) -> None:
        assert refused_fields(read_audit(booking, administrator, **params)) == {field}

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_anybody_but_an_administrator_is_refused(
        self, booking: BookingClient, session: Session, factory: Factory, role: UserRole
    ) -> None:
        account = factory.user(
            role=role, branch=factory.branch() if role is UserRole.COUNTER_STAFF else None
        )
        session.commit()
        refused = read_audit(booking, account)
        assert refused.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(refused) == "authorisation-failure"

    def test_a_caller_with_no_credential_is_refused(self, booking: BookingClient) -> None:
        assert booking.client.get(AUDIT_EVENTS_PATH).status_code == status.HTTP_401_UNAUTHORIZED
