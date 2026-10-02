"""Quoting a hire, with no database and no HTTP.

The quote service depends on the catalogue port, the pricing policy port and
the clock, so one fake and a clock that stands still are all it takes to run
it here. What is proved is what the service decides for itself. Which question
may be asked, which parameter a refusal names, that the policy is handed a
snapshot and never the catalogue entry, and that the discount is an input.

The arithmetic is proved in tests/unit/test_pricing_policy.py and the HTTP
shape in tests/api/test_quote.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

import pytest

from app.application.availability.hire_request import (
    ensure_quantity_in_range,
    ensure_within_hire_limits,
    requested_period,
)
from app.application.catalogue.read_models import ModelDetail
from app.application.money.quote import ModelQuote, QuoteHire, snapshot_of
from app.application.refusal import refused_parameter_of
from app.domain.errors import NotFound, ValidationFailure
from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies import (
    FixedRatePricingPolicy,
    HireQuote,
    LineSnapshot,
    PricingBasis,
    StandardPricingPolicy,
)
from tests.support.clock import FixedClock

HAMMER = ModelDetail(
    sku="TSH-PM-0001",
    slug="bosch-gbh-2-26-rotary-hammer",
    name="Bosch GBH 2-26 Rotary Hammer",
    manufacturer="Bosch",
    model_number="GBH 2-26 DRE",
    category_code="BREAKING",
    category_name="Breaking and Drilling",
    short_description="An SDS-plus rotary hammer.",
    daily_rate=Decimal("280.00"),
    weekly_rate=Decimal("1120.00"),
    deposit_amount=Decimal("1200.00"),
    min_hire_days=2,
    max_hire_days=14,
    image_path=None,
    long_description=None,
    late_fee_per_day=Decimal("120.00"),
)
# The fixed clock says today is Monday the second of March 2026.
TODAY = date(2026, 3, 2)
NINTH = date(2026, 3, 9)
TWELFTH = date(2026, 3, 12)
NINETEENTH = date(2026, 3, 19)


@dataclass
class OneModelCatalogue:
    """A catalogue port holding one published model, which can be repriced."""

    model: ModelDetail = HAMMER
    lookups: list[str] = field(default_factory=list)

    def find_model(self, slug: str) -> ModelDetail | None:
        """Remember the lookup and return the model when asked for by its slug."""
        self.lookups.append(slug)
        return self.model if slug == self.model.slug else None


@dataclass
class RecordingPolicy:
    """A pricing policy that remembers what it was asked and prices as the standard one."""

    asked: list[tuple[LineSnapshot, BookingPeriod, Decimal]] = field(default_factory=list)

    def name(self) -> str:
        """Return the name the policy is logged under."""
        return "recording"

    def quote(
        self, line: LineSnapshot, period: BookingPeriod, discount_percent: Decimal
    ) -> HireQuote:
        """Remember the question and answer it as the standard policy would."""
        self.asked.append((line, period, discount_percent))
        return StandardPricingPolicy().quote(line, period, discount_percent)


@pytest.fixture
def catalogue() -> OneModelCatalogue:
    """Return the catalogue the service under test reads."""
    return OneModelCatalogue()


@pytest.fixture
def policy() -> RecordingPolicy:
    """Return the policy the service under test prices with."""
    return RecordingPolicy()


@pytest.fixture
def service(catalogue: OneModelCatalogue, policy: RecordingPolicy) -> QuoteHire:
    """Return the quote service on the fakes and a clock that stands still."""
    return QuoteHire(catalogue, policy, FixedClock())  # type: ignore[arg-type]  # a partial fake


class TestAQuoteThatIsGiven:
    """The policy is handed a snapshot, and its answer is passed back untouched."""

    def test_the_policy_is_asked_with_a_snapshot_of_the_rates_and_the_period(
        self, service: QuoteHire, policy: RecordingPolicy
    ) -> None:
        answer = service.for_model(HAMMER.slug, NINTH, NINETEENTH, 2)

        assert policy.asked == [
            (
                LineSnapshot(
                    daily_rate=Money.create("280.00"),
                    weekly_rate=Money.create("1120.00"),
                    deposit=Money.create("1200.00"),
                    quantity=2,
                ),
                BookingPeriod(NINTH, NINETEENTH),
                Decimal("0.00"),
            )
        ]
        assert isinstance(answer, ModelQuote)
        assert answer.slug == HAMMER.slug
        assert answer.quote.basis is PricingBasis.WEEKLY
        assert answer.quote.total_inc_vat == Money.create("4508.00")
        assert answer.late_fee_per_day == Money.create("120.00")

    def test_no_discount_is_applied_unless_the_caller_passes_one(
        self, service: QuoteHire, policy: RecordingPolicy
    ) -> None:
        plain = service.for_model(HAMMER.slug, NINTH, TWELFTH, 1)
        trade = service.for_model(HAMMER.slug, NINTH, TWELFTH, 1, Decimal("10.00"))

        assert [asked[2] for asked in policy.asked] == [Decimal("0.00"), Decimal("10.00")]
        assert plain.quote.discount_amount == Money.create("0.00")
        assert trade.quote.discount_amount == Money.create("84.00")
        assert trade.quote.total_inc_vat == Money.create("869.40")

    def test_the_service_prices_with_whichever_policy_it_was_built_with(
        self, catalogue: OneModelCatalogue
    ) -> None:
        fixed = FixedRatePricingPolicy(Money.create("100.00"))
        service = QuoteHire(catalogue, fixed, FixedClock())  # type: ignore[arg-type]  # a partial fake
        answer = service.for_model(HAMMER.slug, NINTH, NINETEENTH, 2)
        assert answer.quote.subtotal_ex_vat == Money.create("200.00")


class TestASnapshotOutlivesACatalogueChange:
    """BR-20, with the case the design document gives."""

    def test_a_snapshot_at_r280_still_prices_at_r280_after_the_rate_becomes_r310(
        self, catalogue: OneModelCatalogue
    ) -> None:
        period = BookingPeriod(NINTH, TWELFTH)
        booked = snapshot_of(catalogue.model, 1)
        before = StandardPricingPolicy().quote(booked, period, Decimal("0.00"))

        catalogue.model = replace(HAMMER, daily_rate=Decimal("310.00"))

        after = StandardPricingPolicy().quote(booked, period, Decimal("0.00"))
        new_booking = StandardPricingPolicy().quote(
            snapshot_of(catalogue.model, 1), period, Decimal("0.00")
        )
        assert after == before
        assert after.unit_amount_ex_vat == Money.create("840.00")
        assert new_booking.unit_amount_ex_vat == Money.create("930.00")


class TestAQuoteThatIsRefused:
    """Held to the limits of a booking, and refused before anything is priced."""

    @pytest.mark.parametrize(
        ("start", "end", "quantity", "parameter"),
        [
            (TWELFTH, NINTH, 1, "to"),
            (NINTH, NINTH, 1, "to"),
            (NINTH, date(2026, 4, 7), 1, "to"),
            (date(2026, 3, 1), NINTH, 1, "from"),
            (date(2026, 6, 1), date(2026, 6, 3), 1, "from"),
            (NINTH, TWELFTH, 0, "quantity"),
            (NINTH, TWELFTH, 11, "quantity"),
            (NINTH, date(2026, 3, 10), 1, "to"),
            (NINTH, date(2026, 3, 24), 1, "to"),
        ],
    )
    def test_a_refusal_names_the_parameter_and_nothing_is_priced(
        self,
        service: QuoteHire,
        policy: RecordingPolicy,
        start: date,
        end: date,
        quantity: int,
        parameter: str,
    ) -> None:
        with pytest.raises(ValidationFailure) as raised:
            service.for_model(HAMMER.slug, start, end, quantity)
        assert refused_parameter_of(raised.value) == parameter
        assert policy.asked == []

    def test_a_bad_period_is_refused_before_the_catalogue_is_read(
        self, service: QuoteHire, catalogue: OneModelCatalogue
    ) -> None:
        with pytest.raises(ValidationFailure):
            service.for_model(HAMMER.slug, TWELFTH, NINTH, 1)
        assert catalogue.lookups == []

    def test_a_slug_no_published_model_carries_is_not_found(
        self, service: QuoteHire, policy: RecordingPolicy
    ) -> None:
        with pytest.raises(NotFound) as raised:
            service.for_model("no-such-model", NINTH, TWELFTH, 1)
        assert raised.value.detail == {"slug": "no-such-model"}
        assert policy.asked == []


class TestWhatMayBeAskedAboutAHire:
    """The checks a search and a quote share, and what each one tells the log."""

    def test_a_period_a_booking_would_accept_is_returned(self) -> None:
        assert requested_period(NINTH, TWELFTH, TODAY) == BookingPeriod(NINTH, TWELFTH)

    def test_a_reversed_period_carries_its_rule_and_its_dates_beside_the_sentence(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            requested_period(TWELFTH, NINTH, TODAY)
        failure = raised.value
        assert failure.message == "The return date has to be after the start date."
        assert failure.rule == "BR-03"
        assert failure.detail["from"] == "2026-03-12"
        assert failure.detail["to"] == "2026-03-09"
        assert failure.detail["hire_days"] == -3

    def test_a_start_in_the_past_carries_its_rule_and_its_dates_beside_the_sentence(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            requested_period(date(2026, 3, 1), NINTH, TODAY)
        failure = raised.value
        assert failure.message == "The hire has to start today or later."
        assert failure.rule == "BR-04"
        assert failure.detail["from"] == "2026-03-01"
        assert failure.detail["today"] == "2026-03-02"

    def test_a_start_beyond_the_horizon_names_its_rule(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            requested_period(date(2026, 6, 1), date(2026, 6, 3), TODAY)
        assert raised.value.message == "A hire can start at most 90 days from today."
        assert raised.value.rule == "BR-05"

    def test_a_quantity_a_line_could_carry_is_accepted(self) -> None:
        ensure_quantity_in_range(1)
        ensure_quantity_in_range(10)

    def test_a_quantity_out_of_range_is_refused_in_a_sentence(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            ensure_quantity_in_range(11)
        assert raised.value.message == "You can hire between 1 and 10 of one tool at a time."
        assert raised.value.detail["received"] == 11

    def test_a_hire_longer_than_the_model_allows_is_refused_in_a_sentence(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            ensure_within_hire_limits(HAMMER, BookingPeriod(NINTH, date(2026, 3, 24)))
        assert raised.value.message == "This tool can be hired for at most 14 days."
        assert raised.value.rule == "BR-03"
        assert raised.value.detail["hire_days"] == 15

    def test_a_hire_shorter_than_the_model_allows_is_refused_in_a_sentence(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            ensure_within_hire_limits(HAMMER, BookingPeriod(NINTH, date(2026, 3, 10)))
        assert raised.value.message == "This tool has to be hired for at least 2 days."

    def test_one_day_is_written_as_one_day(self) -> None:
        one_day_only = replace(HAMMER, min_hire_days=1, max_hire_days=1)
        with pytest.raises(ValidationFailure) as raised:
            ensure_within_hire_limits(one_day_only, BookingPeriod(NINTH, TWELFTH))
        assert raised.value.message == "This tool can be hired for at most 1 day."

    def test_a_hire_inside_the_limits_of_the_model_is_accepted(self) -> None:
        ensure_within_hire_limits(HAMMER, BookingPeriod(NINTH, TWELFTH))
