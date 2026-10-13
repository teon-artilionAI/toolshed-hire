"""Anonymising a customer at their request, through HTTP (#113).

The owner names the customer and gives a reason. The answer is the customer as
the counter now reads them, a "Former customer" with no real contact details,
and behind it the profile, the account, the sessions and every note typed about
them on their booking, hire, damage report, waived charge and confirmation are
written over. The hire and its charges stay, linked to the profile. The audit
event names the trigger and the reason, and no value the customer had. Counter
staff and customers are refused with 403, an unknown customer with 404, and a
customer anonymised already or with something open with 409. These run against
the in memory database on the still clock.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi import status
from httpx import Response
from sqlmodel import Session, col, select

from app.application.identity.anonymise_customer import CUSTOMER_ANONYMISED_ACTION
from app.domain.anonymisation import (
    ANONYMISED_DISPLAY_NAME,
    ANONYMISED_ID_DIGITS,
    ANONYMISED_TEXT,
    REMOVED_NOTE,
    anonymised_email,
)
from app.domain.enums import RentalStatus, ReservationStatus, RevokeReason, UserRole
from app.infrastructure.models import (
    AuditEvent,
    Charge,
    CustomerProfile,
    DamageReport,
    Notification,
    RefreshSession,
    Rental,
    RentalItem,
    Reservation,
    UserAccount,
)
from app.infrastructure.notification import FakeEmailGateway
from tests.api.role_matrix import NOBODYS_KEY
from tests.support.admin_user_api import (
    CUSTOMER_MEMBERS,
    field_refused,
    people_client,
    refused_with,
)
from tests.support.anonymisation_world import (
    TYPED_DAMAGE,
    TYPED_NOTE,
    TYPED_WAIVER,
    CustomerHistory,
    build_customer_history,
)
from tests.support.booking_api import BookingClient, answered
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD, Factory
from tests.support.sessions import LOGIN_PATH

REASON = "The customer asked by email for their details to be removed."


def anonymise_path(customer_id: object) -> str:
    """Return the route that anonymises one customer."""
    return f"/api/admin/customers/{customer_id}/anonymise"


def anonymise(
    people: BookingClient, account: UserAccount, customer_id: object, reason: object = REASON
) -> Response:
    """Ask, as `account`, for a customer to be anonymised."""
    return people.client.post(
        anonymise_path(customer_id), json={"reason": reason}, headers=people.headers(account)
    )


@pytest.fixture
def history(session: Session, factory: Factory) -> CustomerHistory:
    """Commit a customer whose hire is settled and who has notes typed about them."""
    built = build_customer_history(factory)
    session.commit()
    return built


@pytest.fixture
def people(
    session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
) -> Iterator[BookingClient]:
    """Yield the routes on the in memory database."""
    with people_client(session, still_clock, email_gateway) as client:
        yield client


class TestTheOwnerAnonymises:
    """The answer, the rows written over and the rows kept."""

    def test_the_answer_is_a_former_customer_with_no_contact_details(
        self, people: BookingClient, history: CustomerHistory
    ) -> None:
        profile_id = history.world.profile.id
        body = answered(anonymise(people, history.owner, profile_id))
        assert set(body) == CUSTOMER_MEMBERS
        assert (body["displayName"], body["phone"], body["idDocumentLast4"]) == (
            ANONYMISED_DISPLAY_NAME,
            ANONYMISED_TEXT,
            ANONYMISED_ID_DIGITS,
        )
        assert (body["billingSuburb"], body["billingCity"]) == (ANONYMISED_TEXT, ANONYMISED_TEXT)
        assert body["email"] == anonymised_email(profile_id)
        assert body["anonymisedAt"] is not None

    def test_the_profile_and_the_account_are_written_over_and_the_account_stops(
        self, session: Session, people: BookingClient, history: CustomerHistory
    ) -> None:
        answered(anonymise(people, history.owner, history.world.profile.id))
        session.expire_all()
        profile = session.get(CustomerProfile, history.world.profile.id)
        account = session.get(UserAccount, history.world.customer.id)
        assert profile is not None and account is not None
        assert profile.billing_address_line1 == ANONYMISED_TEXT
        assert profile.billing_postal_code == ANONYMISED_TEXT
        assert profile.vat_number is None and profile.company_name is None
        assert profile.anonymised_at is not None
        assert (account.full_name, account.phone, account.is_active) == (
            ANONYMISED_DISPLAY_NAME,
            None,
            False,
        )
        sessions = session.exec(
            select(RefreshSession).where(col(RefreshSession.user_account_id) == account.id)
        ).all()
        assert {row.revoked_reason for row in sessions} == {RevokeReason.ADMIN_REVOKE}
        assert {(row.user_agent, row.ip_address) for row in sessions} == {(None, None)}

    def test_what_was_typed_is_cleared_and_the_hire_and_its_charges_stay(
        self, session: Session, people: BookingClient, history: CustomerHistory
    ) -> None:
        answered(anonymise(people, history.owner, history.world.profile.id))
        session.expire_all()
        booking = session.get(Reservation, history.booked.reservation.id)
        item = session.get(RentalItem, history.item.id)
        report = session.get(DamageReport, history.report.id)
        waived = session.get(Charge, history.waived.id)
        notification = session.get(Notification, history.notification.id)
        rental = session.get(Rental, history.rental.id)
        assert booking is not None and item is not None and report is not None
        assert waived is not None and notification is not None and rental is not None
        assert (booking.notes, booking.cancellation_reason) == (None, REMOVED_NOTE)
        assert item.notes is None
        assert (report.description, report.resolution_notes) == (REMOVED_NOTE, None)
        assert waived.waiver_reason == REMOVED_NOTE
        assert (waived.amount_inc_vat, waived.description) == (
            history.waived.amount_inc_vat,
            "Cleaning of returned equipment",
        )
        assert notification.recipient_email == anonymised_email(history.world.profile.id)
        assert notification.last_error is None
        assert booking.customer_profile_id == history.world.profile.id
        assert (rental.status, rental.deposit_held) == (
            RentalStatus.SETTLED,
            history.rental.deposit_held,
        )
        stored = " ".join(
            str(value)
            for value in (booking.notes, item.notes, report.description, waived.waiver_reason)
        )
        assert not any(typed in stored for typed in (TYPED_NOTE, TYPED_DAMAGE, TYPED_WAIVER))

    def test_the_event_names_the_trigger_and_the_reason_and_no_old_value(
        self, session: Session, people: BookingClient, history: CustomerHistory
    ) -> None:
        answered(anonymise(people, history.owner, history.world.profile.id))
        event = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == CUSTOMER_ANONYMISED_ACTION)
        ).one()
        assert (event.entity_id, event.actor_user_id) == (
            history.world.profile.id,
            history.owner.id,
        )
        assert event.before_state is None
        assert event.after_state is not None
        assert (event.after_state["trigger"], event.after_state["reason"]) == ("request", REASON)
        written = str(event.after_state)
        for old in (
            history.world.customer.email,
            history.world.customer.full_name,
            "082 441 7719",
            "27 Durham Avenue",
            "4189",
        ):
            assert old not in written

    def test_the_customer_cannot_sign_in_afterwards(
        self, people: BookingClient, history: CustomerHistory
    ) -> None:
        profile_id = history.world.profile.id
        old_email = history.world.customer.email
        answered(anonymise(people, history.owner, profile_id))
        for email in (old_email, anonymised_email(profile_id)):
            response = people.client.post(
                LOGIN_PATH, json={"email": email, "password": TEST_PASSWORD}
            )
            assert response.status_code != status.HTTP_200_OK, email


class TestRefusals:
    """Who may ask, for whom, why, and what stops it."""

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_anyone_but_an_administrator_is_refused(
        self,
        session: Session,
        factory: Factory,
        people: BookingClient,
        history: CustomerHistory,
        role: UserRole,
    ) -> None:
        branch = history.world.branch if role is UserRole.COUNTER_STAFF else None
        caller = factory.user(role=role, branch=branch)
        session.commit()
        refused_with(anonymise(people, caller, history.world.profile.id), 403)

    def test_a_customer_nobody_registered_is_not_found(
        self, people: BookingClient, history: CustomerHistory
    ) -> None:
        refused_with(anonymise(people, history.owner, NOBODYS_KEY), 404)

    @pytest.mark.parametrize("reason", ["", "Gone", "x" * 201])
    def test_a_reason_out_of_bounds_is_refused_naming_it(
        self, people: BookingClient, history: CustomerHistory, reason: str
    ) -> None:
        response = anonymise(people, history.owner, history.world.profile.id, reason)
        assert field_refused(response) == ["body.reason"]

    def test_a_customer_anonymised_already_is_refused(
        self, people: BookingClient, history: CustomerHistory
    ) -> None:
        answered(anonymise(people, history.owner, history.world.profile.id))
        problem = refused_with(anonymise(people, history.owner, history.world.profile.id), 409)
        assert problem["detail"] == (
            "This customer was anonymised already, so there is nothing left to remove."
        )

    def test_an_open_booking_and_a_hire_owing_refuse_and_change_nothing(
        self, session: Session, factory: Factory, people: BookingClient
    ) -> None:
        history = build_customer_history(
            factory, rental_status=RentalStatus.RETURNED, balance_due=Decimal("80.00")
        )
        history.booked.reservation.status = ReservationStatus.CONFIRMED
        session.add(history.booked.reservation)
        session.commit()
        problem = refused_with(anonymise(people, history.owner, history.world.profile.id), 409)
        assert problem["detail"] == (
            "This customer still has a booking still open, a hire not yet settled and money "
            "owing on a hire, so their details cannot be removed yet. Finish what is open first."
        )
        session.expire_all()
        profile = session.get(CustomerProfile, history.world.profile.id)
        assert profile is not None
        assert (profile.display_name, profile.anonymised_at) == (
            history.world.customer.full_name,
            None,
        )
        events = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == CUSTOMER_ANONYMISED_ACTION)
        ).all()
        assert events == []
