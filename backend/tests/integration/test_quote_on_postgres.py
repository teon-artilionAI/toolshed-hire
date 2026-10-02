"""A quote worked out from rates held by real PostgreSQL.

The rates are `NUMERIC(12,2)` columns. SQLite has no exact decimal type, so
the fast tests cannot prove that a rate arrives at the pricing policy as the
exact `Decimal` the database holds. This does, through HTTP, with rates whose
cents would not survive a float.

It also runs the rate change of the design document from the other side. A
quote is a question about a new booking, so once the daily rate is raised from
R280 to R310 the next quote is at R310. The snapshot side of BR-20, an existing
booking keeping R280, is proved on the policy in tests/unit.

Every request goes through HTTP with no credential, on a clock that stands
still on the second of March 2026.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.infrastructure.models import ProductModel
from tests.support.catalogue import a_priced_model, model_quote_path, visitor_client
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

TEN_DAYS: Final[dict[str, object]] = {"from": "2026-03-09", "to": "2026-03-19"}
THREE_DAYS: Final[dict[str, object]] = {"from": "2026-03-09", "to": "2026-03-12"}


@pytest.fixture
def visitor(postgres_session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the real database."""
    with visitor_client(postgres_session) as client:
        yield client


def priced_model(
    session: Session, factory: Factory, *, daily: str, weekly: str, deposit: str
) -> ProductModel:
    """Commit a published model at the given rates."""
    model = a_priced_model(
        factory,
        name="Bosch GBH 2-26 Rotary Hammer",
        daily_rate=daily,
        weekly_rate=weekly,
        deposit=deposit,
    )
    session.commit()
    return model


class TestAQuoteFromNumericColumns:
    """The figures the database holds are the figures the policy is handed."""

    def test_the_worked_example_of_the_contract(
        self, visitor: TestClient, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        model = priced_model(
            postgres_session, postgres_factory, daily="280.00", weekly="1120.00", deposit="1200.00"
        )
        response = visitor.get(model_quote_path(model.slug), params={**TEN_DAYS, "quantity": 2})

        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["perUnit"] == {
            "dailyRate": "280.00",
            "weeklyRate": "1120.00",
            "wholeWeeks": 1,
            "remainderDays": 3,
            "basis": "weekly",
            "amountExVat": "1960.00",
        }
        assert body["subtotalExVat"] == "3920.00"
        assert body["vatAmount"] == "588.00"
        assert body["totalIncVat"] == "4508.00"
        assert body["depositTotal"] == "2400.00"

    def test_rates_with_awkward_cents_are_priced_exactly(
        self, visitor: TestClient, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """Three days at R185.90 for seven units is R3,903.90, and 15 percent is R585.585."""
        model = priced_model(
            postgres_session, postgres_factory, daily="185.90", weekly="743.60", deposit="600.10"
        )
        response = visitor.get(model_quote_path(model.slug), params={**THREE_DAYS, "quantity": 7})
        body = response.json()

        assert body["perUnit"]["amountExVat"] == "557.70"
        assert body["subtotalExVat"] == "3903.90"
        assert body["vatAmount"] == "585.59"
        assert body["totalIncVat"] == "4489.49"
        assert body["depositTotal"] == "4200.70"


class TestARateChangeReachesTheNextQuote:
    """Only new bookings take the new rate, and a quote is about a new booking."""

    def test_raising_the_daily_rate_from_r280_to_r310_changes_the_next_quote(
        self, visitor: TestClient, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        model = priced_model(
            postgres_session, postgres_factory, daily="280.00", weekly="1120.00", deposit="1200.00"
        )
        before = visitor.get(model_quote_path(model.slug), params=THREE_DAYS).json()

        model.daily_rate = Decimal("310.00")
        postgres_session.add(model)
        postgres_session.commit()
        after = visitor.get(model_quote_path(model.slug), params=THREE_DAYS).json()

        assert before["perUnit"]["amountExVat"] == "840.00"
        assert after["perUnit"]["amountExVat"] == "930.00"
        assert after["totalIncVat"] == "1069.50"
