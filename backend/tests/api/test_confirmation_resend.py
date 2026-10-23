"""Sending a booking confirmation again (B13.2, US-36).

A customer may re-send their own confirmed booking, and counter staff may
re-send one at their branch. Another customer's booking is a 404, another
branch is a 403, a booking that is not confirmed is a 409, and the fourth
re-send in an hour is a 429. The new notification and its audit event commit
together, and the fake email gateway receives the message.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.domain.enums import ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import AuditEvent, Notification, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.tokens import authorization_header, mint_access_token

PERIOD: Final[BookingPeriod] = BookingPeriod(
    __import__("datetime").date(2026, 10, 20), __import__("datetime").date(2026, 10, 23)
)
RESENT_ACTION: Final[str] = "notification.booking_confirmation_resent"


def bearer(account: UserAccount, clock: FixedClock) -> dict[str, str]:
    """Return the header of an access token for an account, issued at the still clock."""
    token = mint_access_token(
        account.id, role=account.role, branch_id=account.branch_id, issued_at=clock.now()
    )
    return authorization_header(token)


def my_path(reservation_id: object) -> str:
    """Return the customer route for one booking."""
    return f"/api/me/reservations/{reservation_id}/confirmation/resend"


def counter_path(reservation_id: object) -> str:
    """Return the counter route for one booking."""
    return f"/api/counter/reservations/{reservation_id}/confirmation/resend"


@pytest.fixture
def confirmed(
    session: Session, factory: Factory, home_branch
) -> tuple[UserAccount, object]:
    """Return a customer and a confirmed booking of theirs."""
    account = factory.user(email="resend.customer@example.co.za")
    profile = factory.customer_profile(branch=home_branch, account=account)
    reservation = factory.reservation(
        profile=profile, created_by=account, branch=home_branch, period=PERIOD
    )
    reservation.status = ReservationStatus.CONFIRMED
    session.add(reservation)
    session.commit()
    return account, reservation


def notifications_for(session: Session, reservation_id: object) -> list[Notification]:
    """Return the notifications of one booking, oldest first."""
    session.expire_all()
    return list(
        session.exec(
            select(Notification)
            .where(col(Notification.reservation_id) == reservation_id)
            .order_by(col(Notification.queued_at))
        ).all()
    )


def test_a_customer_sends_their_own_confirmation_again(
    account_api: TestClient,
    session: Session,
    still_clock: FixedClock,
    email_gateway,
    confirmed: tuple[UserAccount, object],
) -> None:
    """The route queues a new notification, audits it and sends it."""
    account, reservation = confirmed
    before = len(email_gateway.sent)

    response = account_api.post(my_path(reservation.id), headers=bearer(account, still_clock))

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json() == {"emailDeliverable": True}
    rows = notifications_for(session, reservation.id)
    assert len(rows) == 1
    assert rows[0].recipient_email == account.email
    assert len(email_gateway.sent) == before + 1
    events = list(
        session.exec(select(AuditEvent).where(col(AuditEvent.action) == RESENT_ACTION)).all()
    )
    assert len(events) == 1
    assert events[0].entity_id == reservation.id


def test_another_customers_booking_is_a_404(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    still_clock: FixedClock,
    confirmed: tuple[UserAccount, object],
) -> None:
    """A customer cannot re-send somebody else's confirmation."""
    _owner, reservation = confirmed
    other = factory.user(email="other.resend@example.co.za")
    factory.customer_profile(branch=home_branch, account=other)
    session.commit()
    response = account_api.post(my_path(reservation.id), headers=bearer(other, still_clock))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert problem_code(response) == "not-found"


def test_a_held_booking_is_a_409(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    still_clock: FixedClock,
) -> None:
    """A booking that was never confirmed has no confirmation to send again."""
    account = factory.user(email="held.resend@example.co.za")
    profile = factory.customer_profile(branch=home_branch, account=account)
    reservation = factory.reservation(
        profile=profile, created_by=account, branch=home_branch, period=PERIOD
    )
    session.commit()
    response = account_api.post(my_path(reservation.id), headers=bearer(account, still_clock))
    assert response.status_code == status.HTTP_409_CONFLICT
    assert problem_code(response) == "state-transition"


def test_the_fourth_resend_in_an_hour_is_a_429(
    account_api: TestClient,
    still_clock: FixedClock,
    confirmed: tuple[UserAccount, object],
) -> None:
    """Three are allowed and the fourth waits for the window."""
    account, reservation = confirmed
    headers = bearer(account, still_clock)
    for _ in range(3):
        assert account_api.post(my_path(reservation.id), headers=headers).status_code == 202
    response = account_api.post(my_path(reservation.id), headers=headers)
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers["Retry-After"]


def test_counter_staff_can_send_a_booking_at_their_branch_and_not_another(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    still_clock: FixedClock,
) -> None:
    """The counter route applies the same branch scope every counter write does."""
    other_branch = factory.branch(code="RS2")
    customer = factory.user(email="counter.resend@example.co.za")
    profile = factory.customer_profile(branch=home_branch, account=customer)
    reservation = factory.reservation(
        profile=profile, created_by=customer, branch=other_branch, period=PERIOD
    )
    reservation.status = ReservationStatus.CONFIRMED
    assistant = factory.user(
        role=UserRole.COUNTER_STAFF, branch=home_branch, email="assistant.resend@example.co.za"
    )
    session.add(reservation)
    session.commit()

    refused = account_api.post(
        counter_path(reservation.id), headers=bearer(assistant, still_clock)
    )
    assert refused.status_code == status.HTTP_403_FORBIDDEN
    assert problem_code(refused) == "branch-scope"
