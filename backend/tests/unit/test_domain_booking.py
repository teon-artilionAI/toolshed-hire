"""The reservation, which is the aggregate root of a booking, with no database anywhere.

A reservation is a plain dataclass. These tests build one by hand and ask it
the questions the states and the use cases ask, which is the point of keeping
the domain free of the ORM. A rule proved here holds whatever stores the
booking.

The money on a reservation is the output of the pricing policy (BR-21), worked
out from the figures copied onto each line (BR-20). The worked example is two
rotary hammers and one concrete mixer from the ninth to the twelfth of March
2026, which is three chargeable days with no complete week in them.

The line and the allocation on their own are in test_domain_booking_lines.py.
The moves of the lifecycle are in test_reservation_states.py and
test_reservation_hold_move.py.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Final

import pytest

from app.domain.booking import NOT_YET_PRICED, Reservation, format_reference
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.policies import FixedRatePricingPolicy, StandardPricingPolicy
from tests.support.pricing import rand
from tests.support.reservations import (
    HAMMER,
    HOLD_EXPIRES_AT,
    MIXER,
    ONE_DAY,
    ONE_SECOND,
    REFERENCE,
    RELEASED_AT,
    TWO_LINES,
    a_draft,
    a_product_model,
    a_reservation_in,
    refused_and_untouched,
    releases_of,
)

LATER: Final[datetime] = RELEASED_AT + ONE_DAY
NO_DISCOUNT: Final[Decimal] = Decimal("0.00")
TRADE_DISCOUNT: Final[Decimal] = Decimal("12.50")
# The units that two hammers and one mixer come to.
UNITS: Final[int] = 3
HOLDING_STATUSES: Final[frozenset[ReservationStatus]] = frozenset(
    {ReservationStatus.HELD, ReservationStatus.CONFIRMED, ReservationStatus.COLLECTED}
)
PRICE_FIELDS: Final[tuple[str, ...]] = (
    "daily_rate",
    "weekly_rate",
    "deposit_amount",
    "late_fee_per_day",
    "replacement_value",
)


def figures_of(reservation: Reservation) -> tuple[str, str, str, str]:
    """Return the subtotal, the VAT, the total and the deposit as they are written."""
    return (
        str(reservation.subtotal_ex_vat().amount),
        str(reservation.vat_amount),
        str(reservation.estimated_total_inc_vat),
        str(reservation.deposit_total),
    )


class TestTheReference:
    """The reference a customer quotes at the counter."""

    def test_it_is_the_prefix_the_year_and_a_six_digit_number(self) -> None:
        assert format_reference(2026, 124) == "TSH-R-26-000124"

    def test_only_the_last_two_digits_of_the_year_are_used(self) -> None:
        assert format_reference(2031, 7) == "TSH-R-31-000007"


class TestADraftAndItsLines:
    """A reservation starts as a draft, and a line copies the figures of its model (BR-20)."""

    def test_a_draft_starts_with_no_lines_no_money_and_no_hold(self) -> None:
        reservation = a_draft()
        assert reservation.status is ReservationStatus.DRAFT
        assert reservation.lines == []
        assert reservation.subtotal_ex_vat() == Money.zero()
        assert figures_of(reservation) == ("0", "0.00", "0.00", "0.00")
        assert reservation.discount_percent() == NO_DISCOUNT
        assert reservation.hold_expires_at is None

    def test_a_line_copies_the_five_figures_of_the_product_model(self) -> None:
        line = a_draft().add_line(HAMMER, 2)
        assert (line.product_model_id, line.quantity) == (HAMMER.id, 2)
        assert line.daily_rate_snapshot == Decimal("280.00")
        assert line.weekly_rate_snapshot == Decimal("1120.00")
        assert line.deposit_snapshot == Decimal("1200.00")
        assert line.late_fee_per_day_snapshot == Decimal("140.00")
        assert line.replacement_value_snapshot == Decimal("6500.00")
        assert line.line_subtotal_ex_vat == NOT_YET_PRICED

    def test_lines_are_numbered_from_one_and_belong_to_the_reservation(self) -> None:
        reservation = a_draft()
        first, second = reservation.add_line(HAMMER, 1), reservation.add_line(MIXER, 10)
        assert [first.line_position, second.line_position] == [1, 2]
        assert {first.reservation_id, second.reservation_id} == {reservation.id}
        assert reservation.lines == [first, second]

    @pytest.mark.parametrize("quantity", [-1, 0, 11])
    def test_a_quantity_outside_one_to_ten_is_refused(self, quantity: int) -> None:
        reservation = a_draft((MIXER, 1))
        with refused_and_untouched(reservation, ValidationFailure) as refused:
            reservation.add_line(HAMMER, quantity)
        assert refused.value.message == "You can hire between 1 and 10 of one tool at a time."
        assert refused.value.detail == {"minimum": 1, "maximum": 10, "received": quantity}

    def test_a_product_model_appears_once_in_a_reservation(self) -> None:
        reservation = a_draft((HAMMER, 1))
        with refused_and_untouched(reservation, ValidationFailure) as refused:
            reservation.add_line(HAMMER, 3)
        assert refused.value.detail == {"sku": HAMMER.sku, "reference": REFERENCE}

    @pytest.mark.parametrize(
        "status", [status for status in ReservationStatus if status is not ReservationStatus.DRAFT]
    )
    def test_the_lines_and_the_figures_are_fixed_once_it_is_no_longer_a_draft(
        self, status: ReservationStatus
    ) -> None:
        reservation = a_reservation_in(status)
        with refused_and_untouched(reservation, StateTransitionError) as refused:
            reservation.add_line(MIXER, 1)
        assert (refused.value.from_status, refused.value.to_status) == (status.value, status.value)
        with refused_and_untouched(reservation, StateTransitionError):
            reservation.price_with(StandardPricingPolicy(), NO_DISCOUNT)

    def test_a_later_change_to_the_catalogue_entry_does_not_move_the_line(self) -> None:
        model = a_product_model()
        reservation = a_draft((model, 1))
        before = deepcopy(reservation.lines[0])
        # A catalogue entry is frozen, so I go around that here. It stands for
        # the entry being repriced underneath a booking that already exists.
        for name in PRICE_FIELDS:
            object.__setattr__(model, name, Decimal("1.00"))
        assert reservation.lines[0] == before
        reservation.price_with(StandardPricingPolicy(), NO_DISCOUNT)
        assert reservation.subtotal_ex_vat() == rand("840.00")


class TestPricingAReservation:
    """The totals are the answers of the pricing policy, added up (BR-21)."""

    def test_the_worked_example_at_the_standard_rates(self) -> None:
        # Three days hold no complete week, so one hammer is 3 x R280.00, which
        # is R840.00, and two are R1,680.00. VAT at 15 percent is R252.00 and
        # the total is R1,932.00. The deposit is 2 x R1,200.00.
        reservation = a_draft((HAMMER, 2))
        reservation.price_with(StandardPricingPolicy(), NO_DISCOUNT)
        assert reservation.lines[0].line_subtotal_ex_vat == Decimal("1680.00")
        assert reservation.lines[0].discount_percent == NO_DISCOUNT
        assert figures_of(reservation) == ("1680.00", "252.00", "1932.00", "2400.00")

    def test_a_fixed_rate_prices_a_line_in_one_statement(self) -> None:
        # R100.00 a unit whatever the dates, so two units are R200.00 with R30.00 of VAT.
        reservation = a_draft((HAMMER, 2))
        reservation.price_with(FixedRatePricingPolicy(rand("100.00")), NO_DISCOUNT)
        assert figures_of(reservation) == ("200.00", "30.00", "230.00", "2400.00")

    def test_two_lines_add_up(self) -> None:
        # The mixer is 3 x R450.00, which is R1,350.00, with R202.50 of VAT and
        # a R2,000.00 deposit. It joins the R1,680.00 and R252.00 of the hammers.
        reservation = a_draft(*TWO_LINES)
        reservation.price_with(StandardPricingPolicy(), NO_DISCOUNT)
        subtotal = reservation.subtotal_ex_vat()
        assert isinstance(subtotal, Money)
        assert subtotal.amount == sum(line.line_subtotal_ex_vat for line in reservation.lines)
        assert figures_of(reservation) == ("3030.00", "454.50", "3484.50", "4400.00")

    def test_a_trade_discount_comes_off_the_subtotal_and_is_kept_on_every_line(self) -> None:
        # At 12.5 percent off the hammers are R1,470.00 with R220.50 of VAT.
        # The mixer is R1,181.25, and its VAT of R177.1875 is written as R177.19.
        reservation = a_draft(*TWO_LINES)
        reservation.price_with(StandardPricingPolicy(), TRADE_DISCOUNT)
        assert [line.line_subtotal_ex_vat for line in reservation.lines] == [
            Decimal("1470.00"),
            Decimal("1181.25"),
        ]
        assert {line.discount_percent for line in reservation.lines} == {TRADE_DISCOUNT}
        assert reservation.discount_percent() == TRADE_DISCOUNT
        assert figures_of(reservation) == ("2651.25", "397.69", "3048.94", "4400.00")

    @pytest.mark.parametrize("discount", ["0.00", "7.50", "12.50", "33.33"])
    def test_the_subtotal_and_the_vat_come_to_the_estimated_total(self, discount: str) -> None:
        reservation = a_draft(*TWO_LINES)
        reservation.price_with(StandardPricingPolicy(), Decimal(discount))
        subtotal = reservation.subtotal_ex_vat().amount
        assert subtotal + reservation.vat_amount == reservation.estimated_total_inc_vat

    def test_pricing_again_replaces_the_figures_and_does_not_add_to_them(self) -> None:
        reservation = a_draft(*TWO_LINES)
        reservation.price_with(StandardPricingPolicy(), TRADE_DISCOUNT)
        reservation.price_with(StandardPricingPolicy(), NO_DISCOUNT)
        assert figures_of(reservation) == ("3030.00", "454.50", "3484.50", "4400.00")


class TestWhatTheStatesAskOfAReservation:
    """Whether every unit is held, whether the hold has run out, and letting units go."""

    def test_a_reservation_with_no_lines_is_not_fully_allocated(self) -> None:
        assert not a_draft().is_fully_allocated()

    @pytest.mark.parametrize("status", list(ReservationStatus))
    def test_only_a_held_confirmed_or_collected_reservation_holds_its_units(
        self, status: ReservationStatus
    ) -> None:
        reservation = a_reservation_in(status, TWO_LINES)
        assert reservation.is_fully_allocated() is (status in HOLDING_STATUSES)
        assert reservation.has_active_allocations() is (status in HOLDING_STATUSES)

    def test_one_line_short_of_a_unit_leaves_the_reservation_short(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD, TWO_LINES)
        reservation.lines[1].allocations[0].release(ReleaseReason.REALLOCATED, RELEASED_AT)
        assert not reservation.is_fully_allocated()
        assert reservation.has_active_allocations()

    def test_a_hold_stands_up_to_and_including_the_instant_it_expires_at(self) -> None:
        held = a_reservation_in(ReservationStatus.HELD)
        assert not held.hold_has_expired(HOLD_EXPIRES_AT)
        assert held.hold_has_expired(HOLD_EXPIRES_AT + ONE_SECOND)

    def test_a_reservation_with_no_expiry_has_no_hold_to_run_out(self) -> None:
        assert not a_reservation_in(ReservationStatus.CONFIRMED).hold_has_expired(LATER)

    def test_releasing_counts_the_units_and_stamps_the_reason_and_the_time_together(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED, TWO_LINES)
        assert reservation.release_allocations(ReleaseReason.CANCELLED, LATER) == UNITS
        assert releases_of(reservation) == [(ReleaseReason.CANCELLED, LATER)] * UNITS
        assert reservation.release_allocations(ReleaseReason.EXPIRED, LATER + ONE_SECOND) == 0

    def test_releasing_leaves_an_allocation_that_was_already_released_alone(self) -> None:
        reservation = a_reservation_in(ReservationStatus.CONFIRMED)
        reservation.lines[0].allocations[0].release(ReleaseReason.REALLOCATED, RELEASED_AT)
        assert reservation.release_allocations(ReleaseReason.CANCELLED, LATER) == 1
        assert releases_of(reservation) == [
            (ReleaseReason.REALLOCATED, RELEASED_AT),
            (ReleaseReason.CANCELLED, LATER),
        ]
