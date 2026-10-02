"""The quote route, `GET /api/catalogue/models/{slug}/quote`, which is FR-05.

A visitor sees what a hire will cost before reserving it. The shape of the
answer is fixed by the contract the frontend is written against, so it is
asserted whole. Money is a string with two decimals in every member.

The route works out nothing. It hands the question to the pricing policy and
writes out what comes back, and two tests hold it to that. One prices the same
hires with the policy directly and compares every figure. The other swaps the
policy and watches the answer follow it.

The refusals of the route are in tests/api/test_quote_refusals.py.

The clock stands still on Monday the second of March 2026. The model is the
rotary hammer of the seed data, R280.00 a day and R1,120.00 a week.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.pricing_deps import get_pricing_policy
from app.api.security_headers import CACHE_CONTROL_NO_STORE_VALUE
from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies import FixedRatePricingPolicy, LineSnapshot, StandardPricingPolicy
from app.main import app as production_app
from tests.support.catalogue import a_priced_model, model_quote_path, visitor_client
from tests.support.factories import Factory
from tests.support.log_capture import LogCapture

NINTH: Final[str] = "2026-03-09"
TWELFTH: Final[str] = "2026-03-12"
NINETEENTH: Final[str] = "2026-03-19"
THREE_DAYS: Final[dict[str, object]] = {"from": NINTH, "to": TWELFTH}
TEN_DAYS: Final[dict[str, object]] = {"from": NINTH, "to": NINETEENTH}
MONEY_MEMBERS: Final[tuple[str, ...]] = (
    "subtotalExVat",
    "discountPercent",
    "discountAmount",
    "vatRate",
    "vatAmount",
    "totalIncVat",
    "depositPerUnit",
    "depositTotal",
    "lateFeePerDay",
)
QUOTE_PRICED: Final[str] = "quote.priced"


@pytest.fixture
def visitor(session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the in memory database."""
    with visitor_client(session) as client:
        yield client


@pytest.fixture
def hammer_slug(session: Session, factory: Factory) -> str:
    """Return the slug of a committed rotary hammer, hired for one to fourteen days."""
    model = a_priced_model(
        factory,
        name="Bosch GBH 2-26 Rotary Hammer",
        daily_rate="280.00",
        weekly_rate="1120.00",
        deposit="1200.00",
        max_hire_days=14,
    )
    session.commit()
    return model.slug


class TestTheShapeOfAQuote:
    """Exactly what the contract says, member for member."""

    def test_a_week_and_three_days_for_two_units_is_the_worked_example(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        response = visitor.get(model_quote_path(hammer_slug), params={**TEN_DAYS, "quantity": 2})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "from": NINTH,
            "to": NINETEENTH,
            "hireDays": 10,
            "quantity": 2,
            "perUnit": {
                "dailyRate": "280.00",
                "weeklyRate": "1120.00",
                "wholeWeeks": 1,
                "remainderDays": 3,
                "basis": "weekly",
                "amountExVat": "1960.00",
            },
            "subtotalExVat": "3920.00",
            "discountPercent": "0.00",
            "discountAmount": "0.00",
            "vatRate": "15.00",
            "vatAmount": "588.00",
            "totalIncVat": "4508.00",
            "depositPerUnit": "1200.00",
            "depositTotal": "2400.00",
            "lateFeePerDay": "120.00",
        }

    def test_under_a_week_the_basis_is_daily_and_the_quantity_is_one_when_left_out(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        body = visitor.get(model_quote_path(hammer_slug), params=THREE_DAYS).json()

        assert body["quantity"] == 1
        assert body["hireDays"] == 3
        assert body["perUnit"]["basis"] == "daily"
        assert (body["perUnit"]["wholeWeeks"], body["perUnit"]["remainderDays"]) == (0, 3)
        assert body["perUnit"]["amountExVat"] == body["subtotalExVat"] == "840.00"
        assert body["vatAmount"] == "126.00"
        assert body["totalIncVat"] == "966.00"
        assert body["depositTotal"] == "1200.00"

    def test_money_is_always_a_string_with_two_decimals(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        body = visitor.get(model_quote_path(hammer_slug), params=THREE_DAYS).json()
        amounts = [body[member] for member in MONEY_MEMBERS]
        per_unit = body["perUnit"]
        amounts += [per_unit[member] for member in ("dailyRate", "weeklyRate", "amountExVat")]
        for amount in amounts:
            assert isinstance(amount, str)
            whole, _, cents = amount.partition(".")
            assert whole.isdigit() and len(cents) == 2 and cents.isdigit()

    def test_the_deposit_is_shown_beside_the_total_and_is_not_in_it(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        body = visitor.get(model_quote_path(hammer_slug), params=THREE_DAYS).json()
        charged = Decimal(body["subtotalExVat"]) - Decimal(body["discountAmount"])
        assert Decimal(body["totalIncVat"]) == charged + Decimal(body["vatAmount"])
        assert Decimal(body["totalIncVat"]) < Decimal(body["depositTotal"])

    def test_no_trade_discount_is_applied_on_this_route(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        body = visitor.get(model_quote_path(hammer_slug), params=THREE_DAYS).json()
        assert (body["discountPercent"], body["discountAmount"]) == ("0.00", "0.00")

    def test_a_quote_is_never_stored_by_a_cache(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        response = visitor.get(model_quote_path(hammer_slug), params=THREE_DAYS)
        assert response.headers["Cache-Control"] == CACHE_CONTROL_NO_STORE_VALUE

    def test_a_start_today_and_the_longest_hire_of_the_model_are_quoted(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        response = visitor.get(
            model_quote_path(hammer_slug), params={"from": "2026-03-02", "to": "2026-03-16"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["perUnit"]["wholeWeeks"] == 2


class TestTheRouteWorksOutNothingItself:
    """Every figure is the pricing policy's, so the price exists in one place."""

    @pytest.mark.parametrize(
        ("end", "quantity"),
        [(TWELFTH, 1), ("2026-03-15", 4), ("2026-03-16", 1), (NINETEENTH, 2), ("2026-03-23", 10)],
    )
    def test_the_route_and_the_policy_agree_to_the_cent(
        self, visitor: TestClient, hammer_slug: str, end: str, quantity: int
    ) -> None:
        body = visitor.get(
            model_quote_path(hammer_slug), params={"from": NINTH, "to": end, "quantity": quantity}
        ).json()

        expected = StandardPricingPolicy().quote(
            LineSnapshot(
                daily_rate=Money.create("280.00"),
                weekly_rate=Money.create("1120.00"),
                deposit=Money.create("1200.00"),
                quantity=quantity,
            ),
            BookingPeriod(date.fromisoformat(NINTH), date.fromisoformat(end)),
            Decimal("0.00"),
        )
        assert body["perUnit"]["amountExVat"] == str(expected.unit_amount_ex_vat.amount)
        assert body["perUnit"]["basis"] == expected.basis.value.lower()
        assert body["subtotalExVat"] == str(expected.subtotal_ex_vat.amount)
        assert body["discountAmount"] == str(expected.discount_amount.amount)
        assert body["vatAmount"] == str(expected.vat_amount.amount)
        assert body["totalIncVat"] == str(expected.total_inc_vat.amount)
        assert body["depositTotal"] == str(expected.deposit_total.amount)

    def test_the_answer_follows_whichever_policy_the_application_was_given(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        fixed = FixedRatePricingPolicy(Money.create("100.00"))
        production_app.dependency_overrides[get_pricing_policy] = lambda: fixed
        try:
            body = visitor.get(
                model_quote_path(hammer_slug), params={**TEN_DAYS, "quantity": 2}
            ).json()
        finally:
            production_app.dependency_overrides.pop(get_pricing_policy, None)

        assert body["perUnit"]["amountExVat"] == "100.00"
        assert body["subtotalExVat"] == "200.00"
        assert body["vatAmount"] == "30.00"
        assert body["totalIncVat"] == "230.00"

    def test_the_application_prices_with_the_standard_policy(self) -> None:
        assert isinstance(get_pricing_policy(), StandardPricingPolicy)

    def test_the_log_says_which_policy_priced_the_hire_and_what_it_came_to(
        self, visitor: TestClient, hammer_slug: str, application_log: LogCapture
    ) -> None:
        visitor.get(model_quote_path(hammer_slug), params={**TEN_DAYS, "quantity": 2})

        line = application_log.only(QUOTE_PRICED)
        assert line["slug"] == hammer_slug
        assert line["pricing_policy"] == "standard"
        assert line["basis"] == "WEEKLY"
        assert line["period"] == "[2026-03-09,2026-03-19)"
        assert line["quantity"] == 2
        assert line["total_inc_vat"] == "4508.00"
