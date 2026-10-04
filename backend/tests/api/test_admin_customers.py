"""The customer holds through HTTP (BR-18, US-35).

The administrator lists the customers by name, narrowed by their standing and
searched the way the counter searches, each as the `CustomerSummary` the
counter reads. Putting a customer on hold or blacklisting them refuses their
next booking through the rule every booking asks, and releasing the hold lets
them book again with the count of bookings they did not collect unchanged.
Every change keeps its reason in the audit event. These run against the in
memory database on the still clock.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import AccountStatus, UserRole
from app.infrastructure.models import AuditEvent, Branch, CustomerProfile, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.api.role_matrix import NOBODYS_KEY
from tests.support.admin_api import PAGE_MEMBERS
from tests.support.admin_user_api import (
    CUSTOMER_MEMBERS,
    HOLD_REASON,
    actions_about,
    field_refused,
    list_customers,
    people_client,
    refused_with,
    set_standing,
)
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory

ACCOUNT_ON_HOLD_PROBLEM = "https://toolshedhire.co.za/problems/account-on-hold"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Commit a branch, a hammer and a customer who can book it."""
    built = build_booking_world(factory)
    built.profile.no_show_count = 3
    session.add(built.profile)
    session.commit()
    return built


@pytest.fixture
def owner(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return the committed owner, an administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def people(
    session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
) -> Iterator[BookingClient]:
    """Yield the routes on the in memory database."""
    with people_client(session, still_clock, email_gateway) as client:
        yield client


def walk_in(factory: Factory, session: Session, branch: Branch, name: str) -> CustomerProfile:
    """Commit a walk-in customer with a name."""
    profile = factory.customer_profile(branch=branch)
    profile.display_name = name
    session.add(profile)
    session.commit()
    return profile


def names(page: dict[str, object]) -> list[object]:
    """Return the names on a page of customers, in order."""
    items = page["items"]
    assert isinstance(items, list)
    return [item["displayName"] for item in items]


class TestTheList:
    """Customers by name, narrowed by standing and searched as the counter searches."""

    def test_the_customers_are_listed_by_name_as_the_counter_reads_them(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
    ) -> None:
        walk_in(factory, session, world.branch, "Aaron Petersen")
        page = answered(list_customers(people, owner))
        assert set(page) == PAGE_MEMBERS
        assert names(page) == ["Aaron Petersen", world.profile.display_name]
        items = page["items"]
        assert isinstance(items, list)
        assert set(items[1]) == CUSTOMER_MEMBERS
        assert (items[1]["noShowCount"], items[1]["accountStatus"]) == (3, "ACTIVE")

    def test_the_list_is_narrowed_by_standing_and_searched(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
    ) -> None:
        held = walk_in(factory, session, world.branch, "Aaron Petersen")
        held.account_status = AccountStatus.ON_HOLD
        barred = walk_in(factory, session, world.branch, "Zola Barred")
        barred.account_status = AccountStatus.BLACKLISTED
        session.add_all([held, barred])
        session.commit()

        def listed(**params: object) -> list[object]:
            return names(answered(list_customers(people, owner, **params)))

        assert listed(status="ON_HOLD") == ["Aaron Petersen"]
        assert listed(status="BLACKLISTED") == ["Zola Barred"]
        assert listed(status="ACTIVE") == [world.profile.display_name]
        assert listed(q="zola") == ["Zola Barred"]
        assert listed(q="zola", status="ACTIVE") == []
        assert listed(q="0824417719", status="ON_HOLD") == ["Aaron Petersen"]
        assert listed(q="%%") == []
        assert answered(list_customers(people, owner, pageSize=1, page=2))["total"] == 3

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"status": "SUSPENDED"}, "query.status"),
            ({"q": "a"}, "query.q"),
            ({"pageSize": 101}, "query.pageSize"),
            ({"page": 0}, "query.page"),
        ],
    )
    def test_a_parameter_out_of_range_is_named(
        self,
        people: BookingClient,
        owner: UserAccount,
        params: dict[str, object],
        field: str,
    ) -> None:
        assert field_refused(list_customers(people, owner, **params)) == [field]


class TestTheStanding:
    """A hold refuses the next booking, and its release keeps the count of no shows."""

    def test_a_hold_refuses_a_booking_and_its_release_lets_the_customer_book(
        self, session: Session, people: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        summary = answered(set_standing(people, owner, world.profile.id, "ON_HOLD"))
        assert set(summary) == CUSTOMER_MEMBERS
        assert summary["accountStatus"] == "ON_HOLD"
        refused = people.create(world.customer, world.payload())
        assert refused_with(refused, status.HTTP_403_FORBIDDEN)["type"] == (
            ACCOUNT_ON_HOLD_PROBLEM
        )
        released = answered(set_standing(people, owner, world.profile.id, "ACTIVE"))
        assert (released["accountStatus"], released["noShowCount"]) == ("ACTIVE", 3)
        assert people.create(world.customer, world.payload()).status_code == 201
        events = session.exec(
            select(AuditEvent)
            .where(col(AuditEvent.action) == "customer.status_changed")
            .order_by(col(AuditEvent.id))
        ).all()
        assert [(event.before_state, event.after_state) for event in events] == [
            ({"account_status": "ACTIVE"}, {"account_status": "ON_HOLD", "reason": HOLD_REASON}),
            ({"account_status": "ON_HOLD"}, {"account_status": "ACTIVE", "reason": HOLD_REASON}),
        ]
        assert events[0].actor_user_id == owner.id

    def test_a_blacklisted_customer_is_refused_a_booking(
        self, people: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        answered(set_standing(people, owner, world.profile.id, "BLACKLISTED"))
        refused = people.create(world.customer, world.payload())
        assert refused.status_code == status.HTTP_403_FORBIDDEN

    def test_the_standing_a_customer_already_has_changes_nothing(
        self, session: Session, people: BookingClient, owner: UserAccount, world: BookingWorld
    ) -> None:
        answered(set_standing(people, owner, world.profile.id, "ACTIVE"))
        assert actions_about(session, "customer_profile") == []

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            ({"accountStatus": "ON_HOLD"}, "body.reason"),
            ({"accountStatus": "ON_HOLD", "reason": "Late"}, "body.reason"),
            ({"accountStatus": "SUSPENDED", "reason": HOLD_REASON}, "body.accountStatus"),
            ({"reason": HOLD_REASON}, "body.accountStatus"),
            (
                {"accountStatus": "ON_HOLD", "reason": HOLD_REASON, "noShowCount": 0},
                "body.noShowCount",
            ),
        ],
    )
    def test_a_body_that_breaks_a_rule_is_named(
        self,
        session: Session,
        people: BookingClient,
        owner: UserAccount,
        world: BookingWorld,
        body: dict[str, object],
        field: str,
    ) -> None:
        response = people.client.post(
            f"/api/admin/customers/{world.profile.id}/status",
            json=body,
            headers=people.headers(owner),
        )
        assert field_refused(response) == [field]
        assert actions_about(session, "customer_profile") == []

    def test_a_customer_nobody_registered_is_not_found(
        self, people: BookingClient, owner: UserAccount
    ) -> None:
        response = set_standing(people, owner, NOBODYS_KEY, "ACTIVE")
        assert refused_with(response, status.HTTP_404_NOT_FOUND)["type"].endswith("not-found")

    def test_counter_staff_cannot_lift_a_hold(
        self, session: Session, factory: Factory, people: BookingClient, world: BookingWorld
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        response = set_standing(people, assistant, world.profile.id, "ACTIVE")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert list_customers(people, assistant).status_code == status.HTTP_403_FORBIDDEN
