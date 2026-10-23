"""The statement and the data export, through HTTP and real SQL (FR-28, US-27).

A customer reads their own statement for a period and downloads everything
held about them. Another customer's hire is never in either answer, a staff
account is refused, and a signed out caller is refused before any work. The
statement is the ledger's own rows, deposits and charges included, and the
export is built from the personal data map with every credential column left
out.

The tests use the in memory database the rest of the account tests use, and
write the rental and charge rows directly. The checkout flow that normally
writes them is covered by its own tests; these are about what a statement and
an export show once those rows exist.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.domain.enums import ChargeStatus, ChargeType, RentalStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import Branch, Charge, CustomerProfile, Rental, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.tokens import authorization_header, mint_access_token

STATEMENT_PATH: Final[str] = "/api/me/statement"
STATEMENT_CSV_PATH: Final[str] = "/api/me/statement.csv"
EXPORT_PATH: Final[str] = "/api/me/export"
PERIOD: Final[dict[str, str]] = {"from": "2026-10-01", "to": "2026-11-01"}
CHECKOUT: Final[datetime] = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
HIRE_DAYS: Final[BookingPeriod] = BookingPeriod(date(2026, 10, 5), date(2026, 10, 8))
DEPOSIT_HELD: Final[Decimal] = Decimal("1200.00")
DEPOSIT_WITHHELD: Final[Decimal] = Decimal("240.00")
DEPOSIT_REFUNDED: Final[Decimal] = Decimal("960.00")
BALANCE_DUE: Final[Decimal] = Decimal("0.00")
HIRE_CHARGE: Final[Decimal] = Decimal("555.00")
LATE_FEE: Final[Decimal] = Decimal("240.00")
FORMULA_DESCRIPTION: Final[str] = "=1+1"


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
    profile: CustomerProfile,
    branch: Branch,
    reference: str = "TSH-H-26-000901",
    charge_description: str = "Hire of the unit",
) -> Rental:
    """Write one hire with two charges, the way a checkout would have."""
    reservation = factory.reservation(
        profile=profile, created_by=account, branch=branch, period=HIRE_DAYS
    )
    rental = Rental(
        reference=reference,
        reservation_id=reservation.id,
        branch_id=branch.id,
        status=RentalStatus.SETTLED,
        checked_out_at=CHECKOUT,
        checked_out_by_user_id=account.id,
        due_back_on=HIRE_DAYS.end,
        returned_at=CHECKOUT,
        deposit_held=DEPOSIT_HELD,
        deposit_withheld=DEPOSIT_WITHHELD,
        deposit_refunded=DEPOSIT_REFUNDED,
        balance_due=BALANCE_DUE,
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
                description=charge_description,
                amount_ex_vat=HIRE_CHARGE,
                vat_rate=Decimal("15.00"),
                vat_amount=Decimal("0.00"),
                amount_inc_vat=HIRE_CHARGE,
                status=ChargeStatus.SETTLED,
                raised_at=CHECKOUT,
                raised_by_user_id=account.id,
                payment_reference="1",
            ),
            Charge(
                rental_id=rental.id,
                charge_type=ChargeType.LATE_FEE,
                description="Late fee",
                amount_ex_vat=LATE_FEE,
                vat_rate=Decimal("15.00"),
                vat_amount=Decimal("0.00"),
                amount_inc_vat=LATE_FEE,
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
def customer(
    session: Session, factory: Factory, home_branch: Branch
) -> tuple[UserAccount, CustomerProfile]:
    """Return a committed customer with a profile at the home branch."""
    account = factory.user()
    profile = factory.customer_profile(branch=home_branch, account=account)
    session.commit()
    return account, profile


def test_a_customer_reads_only_their_own_statement(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch: Branch,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """The statement has the caller's hire and never another customer's."""
    account, profile = customer
    add_rental(session, factory, account=account, profile=profile, branch=home_branch)
    other_account = factory.user(email="other@example.co.za")
    other_profile = factory.customer_profile(branch=home_branch, account=other_account)
    session.commit()
    add_rental(
        session,
        factory,
        account=other_account,
        profile=other_profile,
        branch=home_branch,
        reference="TSH-H-26-000902",
    )

    response = account_api.get(
        STATEMENT_PATH, params=PERIOD, headers=bearer(account, still_clock)
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert [item["reference"] for item in body["items"]] == ["TSH-H-26-000901"]
    assert body["totals"] == {
        "hireCount": 1,
        "chargesTotalIncVat": "795.00",
        "depositHeld": "1200.00",
        "depositWithheld": "240.00",
        "depositRefunded": "960.00",
        "balanceDue": "0.00",
    }
    assert [charge["description"] for charge in body["items"][0]["charges"]] == [
        "Hire of the unit",
        "Late fee",
    ]


def test_a_statement_is_csv_with_the_ledger_rows_and_escaped_cells(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch: Branch,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """The CSV names its file, streams the rows and escapes a formula."""
    account, profile = customer
    add_rental(
        session,
        factory,
        account=account,
        profile=profile,
        branch=home_branch,
        charge_description=FORMULA_DESCRIPTION,
    )

    response = account_api.get(
        STATEMENT_CSV_PATH, params=PERIOD, headers=bearer(account, still_clock)
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="toolshed-statement-2026-10-01-2026-11-01.csv"'
    )
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    assert "# Statement for" in body
    assert "TSH-H-26-000901" in body
    assert f"'{FORMULA_DESCRIPTION}" in body
    assert "795.00" in body


def test_a_reversed_statement_period_is_refused(
    account_api: TestClient, still_clock: FixedClock, customer: tuple[UserAccount, CustomerProfile]
) -> None:
    """A period that ends before it starts is a 422 that names a bound."""
    account, _profile = customer
    response = account_api.get(
        STATEMENT_PATH,
        params={"from": "2026-11-01", "to": "2026-10-01"},
        headers=bearer(account, still_clock),
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_code(response) == "validation-failure"


def test_a_staff_account_cannot_read_a_statement(
    account_api: TestClient, still_clock: FixedClock, home_branch: Branch, factory: Factory
) -> None:
    """The route admits customers only."""
    admin = factory.user(role=UserRole.ADMIN)
    response = account_api.get(
        STATEMENT_PATH, params=PERIOD, headers=bearer(admin, still_clock)
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_a_signed_out_caller_is_refused(account_api: TestClient) -> None:
    """No token is a 401, before any statement work."""
    response = account_api.get(STATEMENT_PATH, params=PERIOD)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_the_export_has_every_customer_table_and_no_credentials(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch: Branch,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """The export follows the personal data map and leaves secrets out."""
    account, profile = customer
    add_rental(session, factory, account=account, profile=profile, branch=home_branch)

    response = account_api.get(EXPORT_PATH, headers=bearer(account, still_clock))

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="toolshed-my-data-'
    )
    body = response.json()
    tables = body["tables"]
    assert "customer_profile" in tables
    assert "user_account" in tables
    assert "reservation" in tables
    assert "rental" in tables
    assert "charge" in tables
    assert len(tables["rental"]) == 1
    assert len(tables["charge"]) == 2
    assert body["rowCount"] == sum(len(rows) for rows in tables.values())
    flattened = json.dumps(body)
    assert "password_hash" not in flattened
    assert "token_hash" not in flattened
    assert "email_verification_token_hash" not in flattened


def test_the_export_is_audited_and_only_names_counts(
    account_api: TestClient,
    session: Session,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """An export writes one event with counts, never the values."""
    account, _profile = customer
    response = account_api.get(EXPORT_PATH, headers=bearer(account, still_clock))
    assert response.status_code == status.HTTP_200_OK
    from app.infrastructure.models import AuditEvent

    session.expire_all()
    events = list(
        session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "customer.data_exported")
        ).all()
    )
    assert len(events) == 1
    assert events[0].after_state == {
        "table_count": len(response.json()["tables"]),
        "row_count": response.json()["rowCount"],
    }
