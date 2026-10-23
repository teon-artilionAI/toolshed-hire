"""The statement and export query on PostgreSQL (FR-28, US-27).

The statement is read with the joins and the activity condition it will use in
production, and the export follows the foreign keys over the real schema. The
in memory tests cover the HTTP boundary; this one covers the SQL that SQLite
could accept while PostgreSQL would not.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final

from sqlmodel import Session

from app.domain.enums import ChargeStatus, ChargeType, RentalStatus
from app.domain.period import BookingPeriod
from app.infrastructure.models import Charge, CustomerProfile, Rental, UserAccount
from app.infrastructure.personal_data_export import SECRET_COLUMNS, SqlPersonalDataExporter
from app.infrastructure.statement_query import SqlStatementReads
from tests.support.factories import Factory

CHECKOUT: Final[datetime] = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
PERIOD: Final[BookingPeriod] = BookingPeriod(date(2026, 10, 5), date(2026, 10, 8))
REFERENCE: Final[str] = "TSH-H-26-000911"


def _rental_with_charges(
    session: Session, factory: Factory
) -> tuple[UserAccount, CustomerProfile, Rental]:
    """Write one hire with two charges and return its account, profile and row."""
    branch = factory.branch(code="PG1")
    account = factory.user(email="pg.statement@example.co.za")
    profile = factory.customer_profile(branch=branch, account=account)
    reservation = factory.reservation(
        profile=profile, created_by=account, branch=branch, period=PERIOD
    )
    rental = Rental(
        reference=REFERENCE,
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
                description="Hire of the unit",
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
    session.flush()
    return account, profile, rental


def test_the_statement_reads_the_hires_and_charges_of_one_customer(
    postgres_session: Session, postgres_factory: Factory
) -> None:
    """The SQL returns the hire, its deposit figures and both charges."""
    account, profile, _rental = _rental_with_charges(postgres_session, postgres_factory)
    lines = SqlStatementReads(postgres_session).for_customer(
        profile.id, date(2026, 10, 1), date(2026, 11, 1)
    )
    assert len(lines) == 1
    line = lines[0]
    assert line.reference == REFERENCE
    assert line.deposit_held == Decimal("1200.00")
    assert line.deposit_withheld == Decimal("240.00")
    assert line.deposit_refunded == Decimal("960.00")
    assert line.starts_on == date(2026, 10, 5)
    assert [charge.description for charge in line.charges] == [
        "Hire of the unit",
        "Late fee",
    ]
    assert line.charges_total_inc_vat == Decimal("795.00")


def test_the_export_follows_every_key_chain_and_never_names_a_secret(
    postgres_session: Session, postgres_factory: Factory
) -> None:
    """The export reaches the hire and its charges, and no credential column is in it."""
    account, profile, _rental = _rental_with_charges(postgres_session, postgres_factory)
    tables = SqlPersonalDataExporter(postgres_session).export(
        customer_profile_id=profile.id, user_account_id=account.id
    )
    assert len(tables["rental"]) == 1
    assert len(tables["charge"]) == 2
    assert tables["rental"][0]["reference"] == REFERENCE
    exported_names = {
        name for rows in tables.values() for row in rows for name in row
    }
    assert exported_names.isdisjoint(SECRET_COLUMNS)
    assert "password_hash" not in exported_names
    assert "token_hash" not in exported_names
