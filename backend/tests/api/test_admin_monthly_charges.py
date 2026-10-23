"""The month end charge CSV for the bookkeeper (B13.3).

An owner downloads one calendar month of charges, at one branch or all of
them. Every charge is a row, the totals at the end add up to the rows, a
formula in a description is escaped, and the route is for an administrator
alone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.domain.enums import ChargeStatus, ChargeType, RentalStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import Charge, Rental, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.tokens import authorization_header, mint_access_token

CHECKOUT: Final[datetime] = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
PERIOD: Final[BookingPeriod] = BookingPeriod(date(2026, 10, 5), date(2026, 10, 8))
REFERENCE: Final[str] = "TSH-H-26-000921"
MONTH_PATH: Final[str] = "/api/admin/reports/charges.csv"


def bearer(account: UserAccount, clock: FixedClock) -> dict[str, str]:
    """Return the header of an access token for an account, issued at the still clock."""
    token = mint_access_token(
        account.id, role=account.role, branch_id=account.branch_id, issued_at=clock.now()
    )
    return authorization_header(token)


def add_rental(
    session: Session,
    factory: Factory,
    *,
    account: UserAccount,
    branch,
    reference: str = REFERENCE,
    description: str = "Hire of the unit",
) -> Rental:
    """Write one hire with two charges."""
    profile = factory.customer_profile(branch=branch, account=account)
    reservation = factory.reservation(
        profile=profile, created_by=account, branch=branch, period=PERIOD
    )
    rental = Rental(
        reference=reference,
        reservation_id=reservation.id,
        branch_id=branch.id,
        status=RentalStatus.SETTLED,
        checked_out_at=CHECKOUT,
        checked_out_by_user_id=account.id,
        due_back_on=PERIOD.end,
        returned_at=CHECKOUT,
        deposit_held=Decimal("1200.00"),
        deposit_withheld=Decimal("240.00"),
        deposit_refunded=Decimal("960.00"),
        balance_due=Decimal("0.00"),
        settled_at=CHECKOUT,
        agreement_signed=True,
    )
    session.add(rental)
    session.flush()
    session.add_all(
        [
            Charge(
                rental_id=rental.id,
                charge_type=ChargeType.HIRE,
                description=description,
                amount_ex_vat=Decimal("555.00"),
                vat_rate=Decimal("15.00"),
                vat_amount=Decimal("0.00"),
                amount_inc_vat=Decimal("555.00"),
                status=ChargeStatus.SETTLED,
                raised_at=CHECKOUT,
                raised_by_user_id=account.id,
                payment_reference="1",
            ),
            Charge(
                rental_id=rental.id,
                charge_type=ChargeType.LATE_FEE,
                description="Late fee",
                amount_ex_vat=Decimal("240.00"),
                vat_rate=Decimal("15.00"),
                vat_amount=Decimal("0.00"),
                amount_inc_vat=Decimal("240.00"),
                status=ChargeStatus.SETTLED,
                raised_at=CHECKOUT,
                raised_by_user_id=account.id,
                payment_reference="2",
            ),
        ]
    )
    session.commit()
    return rental


@pytest.fixture
def owner(
    session: Session, factory: Factory, still_clock: FixedClock
) -> tuple[UserAccount, dict[str, str]]:
    """Return an administrator and their bearer header."""
    admin = factory.user(role=UserRole.ADMIN)
    session.commit()
    return admin, bearer(admin, still_clock)


def test_the_month_csv_has_every_row_and_reconciled_totals(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    owner: tuple[UserAccount, dict[str, str]],
) -> None:
    """The file names its month, carries both charges and adds up."""
    _admin, headers = owner
    account = factory.user(email="charges@example.co.za")
    add_rental(session, factory, account=account, branch=home_branch, description="=1+1")

    response = account_api.get(MONTH_PATH, params={"month": "2026-10"}, headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="toolshed-charges-2026-10.csv"'
    )
    body = response.text
    assert "# Charges for October 2026 at every branch." in body
    assert REFERENCE in body
    assert "'=1+1" in body
    assert "Totals" in body
    assert "795.00" in body
    assert "2 charges" in body


def test_a_branch_filter_excludes_another_branch(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    owner: tuple[UserAccount, dict[str, str]],
) -> None:
    """Only the named branch's charges are in the file."""
    _admin, headers = owner
    other = factory.branch(code="MC2")
    first = factory.user(email="charges1@example.co.za")
    second = factory.user(email="charges2@example.co.za")
    add_rental(session, factory, account=first, branch=home_branch, reference="TSH-H-26-000931")
    add_rental(session, factory, account=second, branch=other, reference="TSH-H-26-000932")

    response = account_api.get(
        MONTH_PATH, params={"month": "2026-10", "branchCode": home_branch.code}, headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    assert "TSH-H-26-000931" in response.text
    assert "TSH-H-26-000932" not in response.text


def test_a_bad_month_is_refused(
    account_api: TestClient, owner: tuple[UserAccount, dict[str, str]]
) -> None:
    """A month that is not a real YYYY-MM month is a 422 naming it."""
    _admin, headers = owner
    response = account_api.get(MONTH_PATH, params={"month": "2026-13"}, headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "query.month" in problem_of(response)["errors"]["fields"]


def test_counter_staff_are_refused(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch,
    still_clock: FixedClock,
) -> None:
    """The bookkeeper file is for an administrator alone."""
    assistant = factory.user(
        role=UserRole.COUNTER_STAFF, branch=home_branch, email="charges.counter@example.co.za"
    )
    session.commit()
    response = account_api.get(
        MONTH_PATH,
        params={"month": "2026-10"},
        headers=bearer(assistant, still_clock),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert problem_code(response) == "authorisation-failure"
