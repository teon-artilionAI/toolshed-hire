"""The monthly charge query at Cape Town month boundaries (B13.3).

SQLite stores a datetime without its zone, so the fast suite cannot prove this.
This test runs the real query on PostgreSQL, where the charge instants are
timestamps with time zones.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session

from app.domain.enums import ChargeStatus, ChargeType, RentalStatus
from app.domain.period import BookingPeriod
from app.infrastructure.models import Charge, Rental
from app.infrastructure.monthly_charges import SqlMonthlyCharges
from tests.support.factories import Factory

CAPE_TOWN = ZoneInfo("Africa/Johannesburg")
CHECKOUT = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
PERIOD = BookingPeriod(date(2026, 10, 5), date(2026, 10, 8))
ZERO = Decimal("0.00")


@pytest.mark.postgres
class TestTheMonthBoundary:
    """A month is a Cape Town calendar month, not a UTC one."""

    def test_october_includes_cape_town_midnight_and_excludes_november(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """Charges at 00:30 SAST belong to the SAST day, not the UTC day before."""
        branch = postgres_factory.branch()
        account = postgres_factory.user()
        profile = postgres_factory.customer_profile(branch=branch, account=account)
        reservation = postgres_factory.reservation(
            profile=profile, created_by=account, branch=branch, period=PERIOD
        )
        rental = Rental(
            reference="TSH-H-26-000961",
            reservation_id=reservation.id,
            branch_id=branch.id,
            status=RentalStatus.SETTLED,
            checked_out_at=CHECKOUT,
            checked_out_by_user_id=account.id,
            due_back_on=PERIOD.end,
            returned_at=CHECKOUT,
            deposit_held=Decimal("1200.00"),
            deposit_withheld=ZERO,
            deposit_refunded=Decimal("1200.00"),
            balance_due=ZERO,
            settled_at=CHECKOUT,
            agreement_signed=True,
        )
        postgres_session.add(rental)
        postgres_session.flush()
        moments = (
            ("before October", datetime(2026, 9, 30, 23, 30, tzinfo=CAPE_TOWN)),
            ("October start", datetime(2026, 10, 1, 0, 30, tzinfo=CAPE_TOWN)),
            ("October end", datetime(2026, 10, 31, 23, 30, tzinfo=CAPE_TOWN)),
            ("November start", datetime(2026, 11, 1, 0, 30, tzinfo=CAPE_TOWN)),
        )
        for index, (description, raised_at) in enumerate(moments, start=1):
            postgres_session.add(
                Charge(
                    rental_id=rental.id,
                    charge_type=ChargeType.HIRE,
                    description=description,
                    amount_ex_vat=Decimal("100.00"),
                    vat_rate=Decimal("15.00"),
                    vat_amount=Decimal("15.00"),
                    amount_inc_vat=Decimal("115.00"),
                    status=ChargeStatus.SETTLED,
                    raised_at=raised_at,
                    raised_by_user_id=account.id,
                    payment_reference=str(index),
                )
            )
        postgres_session.commit()

        result = SqlMonthlyCharges(postgres_session).read(
            date(2026, 10, 1), date(2026, 11, 1), None
        )

        assert {line.description for line in result.lines} == {
            "October start",
            "October end",
        }

    def test_january_includes_cape_town_midnight_not_december(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """1 January 00:30 SAST is January, not December."""
        branch = postgres_factory.branch()
        account = postgres_factory.user()
        profile = postgres_factory.customer_profile(branch=branch, account=account)
        reservation = postgres_factory.reservation(
            profile=profile, created_by=account, branch=branch, period=PERIOD
        )
        rental = Rental(
            reference="TSH-H-26-000962",
            reservation_id=reservation.id,
            branch_id=branch.id,
            status=RentalStatus.SETTLED,
            checked_out_at=CHECKOUT,
            checked_out_by_user_id=account.id,
            due_back_on=PERIOD.end,
            returned_at=CHECKOUT,
            deposit_held=Decimal("1200.00"),
            deposit_withheld=ZERO,
            deposit_refunded=Decimal("1200.00"),
            balance_due=ZERO,
            settled_at=CHECKOUT,
            agreement_signed=True,
        )
        postgres_session.add(rental)
        postgres_session.flush()
        for index, (description, raised_at) in enumerate(
            (
                ("December start", datetime(2026, 12, 1, 0, 30, tzinfo=CAPE_TOWN)),
                ("January start", datetime(2027, 1, 1, 0, 30, tzinfo=CAPE_TOWN)),
            ),
            start=1,
        ):
            postgres_session.add(
                Charge(
                    rental_id=rental.id,
                    charge_type=ChargeType.HIRE,
                    description=description,
                    amount_ex_vat=Decimal("100.00"),
                    vat_rate=Decimal("15.00"),
                    vat_amount=Decimal("15.00"),
                    amount_inc_vat=Decimal("115.00"),
                    status=ChargeStatus.SETTLED,
                    raised_at=raised_at,
                    raised_by_user_id=account.id,
                    payment_reference=str(index),
                )
            )
        postgres_session.commit()

        december = SqlMonthlyCharges(postgres_session).read(
            date(2026, 12, 1), date(2027, 1, 1), None
        )
        january = SqlMonthlyCharges(postgres_session).read(
            date(2027, 1, 1), date(2027, 2, 1), None
        )

        assert {line.description for line in december.lines} == {"December start"}
        assert {line.description for line in january.lines} == {"January start"}
