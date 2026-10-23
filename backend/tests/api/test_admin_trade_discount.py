"""Setting a customer's trade discount (BR-21).

Only an owner may set it, only on a trade account, and only to a value from 0
up to below 100 with two decimals. The change is written to the profile and to
the audit trail in one transaction, and the next booking copies it onto its
lines. An unchanged value writes nothing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.domain.enums import CustomerType, UserRole
from app.infrastructure.models import AuditEvent, CustomerProfile, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.tokens import authorization_header, mint_access_token

CHANGED_ACTION: Final[str] = "customer.trade_discount_changed"


def bearer(account: UserAccount, clock: FixedClock) -> dict[str, str]:
    """Return the header of an access token for an account, issued at the still clock."""
    token = mint_access_token(
        account.id, role=account.role, branch_id=account.branch_id, issued_at=clock.now()
    )
    return authorization_header(token)


def path(customer_id: object) -> str:
    """Return the route that sets one customer's discount."""
    return f"/api/admin/customers/{customer_id}/trade-discount"


def profile_row(session: Session, profile_id: object) -> CustomerProfile:
    """Return one profile as the database now holds it."""
    session.expire_all()
    return session.exec(
        select(CustomerProfile).where(col(CustomerProfile.id) == profile_id)
    ).one()


@pytest.fixture
def owner(
    factory: Factory, session: Session, still_clock: FixedClock
) -> tuple[UserAccount, dict[str, str]]:
    """Return an administrator and their bearer header."""
    admin = factory.user(role=UserRole.ADMIN)
    session.commit()
    return admin, bearer(admin, still_clock)


def test_an_owner_sets_the_discount_and_the_audit_keeps_both_values(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    owner: tuple[UserAccount, dict[str, str]],
) -> None:
    """The profile moves to the new value and one event names the old and new."""
    _admin, headers = owner
    account = factory.user(email="trade@example.co.za")
    profile = factory.customer_profile(
        branch=home_branch, account=account, customer_type=CustomerType.TRADE
    )
    session.commit()

    response = account_api.post(
        path(profile.id), json={"tradeDiscountPercent": "12.50"}, headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["tradeDiscountPercent"] == "12.50"
    assert profile_row(session, profile.id).trade_discount_percent == Decimal("12.50")
    events = list(
        session.exec(select(AuditEvent).where(col(AuditEvent.action) == CHANGED_ACTION)).all()
    )
    assert len(events) == 1
    assert events[0].before_state == {"tradeDiscountPercent": "0.00"}
    assert events[0].after_state == {"tradeDiscountPercent": "12.50"}


def test_a_value_outside_the_range_is_refused(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    owner: tuple[UserAccount, dict[str, str]],
) -> None:
    """A hundred percent is refused and the profile stays as it was."""
    _admin, headers = owner
    account = factory.user(email="trade2@example.co.za")
    profile = factory.customer_profile(
        branch=home_branch, account=account, customer_type=CustomerType.TRADE
    )
    session.commit()

    response = account_api.post(
        path(profile.id), json={"tradeDiscountPercent": "100.00"}, headers=headers
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "body.tradeDiscountPercent" in problem_of(response)["errors"]["fields"]
    assert profile_row(session, profile.id).trade_discount_percent == Decimal("0.00")


def test_an_individual_customer_has_no_trade_discount(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    owner: tuple[UserAccount, dict[str, str]],
) -> None:
    """An individual account is refused with the field named."""
    _admin, headers = owner
    account = factory.user(email="individual@example.co.za")
    profile = factory.customer_profile(branch=home_branch, account=account)
    session.commit()

    response = account_api.post(
        path(profile.id), json={"tradeDiscountPercent": "5.00"}, headers=headers
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "body.tradeDiscountPercent" in problem_of(response)["errors"]["fields"]


def test_an_unknown_customer_is_a_404(
    account_api: TestClient, owner: tuple[UserAccount, dict[str, str]]
) -> None:
    """A key with no profile is not found."""
    _admin, headers = owner
    response = account_api.post(
        path("00000000-0000-4000-8000-000000000001"),
        json={"tradeDiscountPercent": "5.00"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert problem_code(response) == "not-found"


def test_counter_staff_are_refused(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    still_clock: FixedClock,
) -> None:
    """Only an administrator may set a discount."""
    assistant = factory.user(
        role=UserRole.COUNTER_STAFF, branch=home_branch, email="counter@example.co.za"
    )
    account = factory.user(email="trade3@example.co.za")
    profile = factory.customer_profile(
        branch=home_branch, account=account, customer_type=CustomerType.TRADE
    )
    session.commit()
    response = account_api.post(
        path(profile.id),
        json={"tradeDiscountPercent": "5.00"},
        headers=bearer(assistant, still_clock),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
