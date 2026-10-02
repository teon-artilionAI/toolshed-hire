"""What one caller is shown of a reservation, and what they may do to it next.

`canHold`, `canConfirm` and `canCancel` are worked out on the server, so a
screen never repeats the rules of the lifecycle. These tests pin the whole
table, every status against every kind of caller, so a change to a state or
to who may act shows up here as a changed cell.

Whether a move is legal from a status comes from the reservation states. What
is added is who is asking and what time it is. Counter staff act at their own
branch only (BR-43), a customer needs a verified address to confirm (BR-47),
and a hold that has run out can no longer be confirmed or cancelled (BR-13).

A customer is never shown an asset tag (US-07).

There is no database here. A reservation is built by hand as the read model a
repository would return.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.application.booking.read_models import (
    ReservationDetail,
    ReservationLineDetail,
    ReservationPage,
)
from app.application.booking.views import page_for, view_for
from app.domain.enums import ReservationStatus, UserRole
from app.domain.identity import Actor

NOW: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
HOLD_RUNS_OUT_AT: Final[datetime] = NOW + timedelta(minutes=30)
BRANCH_ID: Final[UUID] = uuid4()
TAGS: Final[tuple[str, ...]] = ("TSH-DR-0042", "TSH-DR-0043")

CUSTOMER: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.CUSTOMER)
COUNTER_HERE: Final[Actor] = Actor(
    user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=BRANCH_ID
)
COUNTER_ELSEWHERE: Final[Actor] = Actor(
    user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=uuid4()
)
ADMINISTRATOR: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN)
# Everybody who may act on a reservation at this branch.
MAY_ACT: Final[tuple[Actor, ...]] = (CUSTOMER, COUNTER_HERE, ADMINISTRATOR)

HOLD: Final[str] = "hold"
CONFIRM: Final[str] = "confirm"
CANCEL: Final[str] = "cancel"
# The moves a caller who may act is offered in each status. Every other cell
# of the table is False.
OFFERED: Final[dict[ReservationStatus, frozenset[str]]] = {
    ReservationStatus.DRAFT: frozenset({HOLD, CANCEL}),
    ReservationStatus.HELD: frozenset({CONFIRM, CANCEL}),
    ReservationStatus.CONFIRMED: frozenset({CANCEL}),
    ReservationStatus.COLLECTED: frozenset(),
    ReservationStatus.RETURNED: frozenset(),
    ReservationStatus.CANCELLED: frozenset(),
    ReservationStatus.NO_SHOW: frozenset(),
    ReservationStatus.EXPIRED: frozenset(),
}
HOLDS_UNITS: Final[frozenset[ReservationStatus]] = frozenset(
    {ReservationStatus.HELD, ReservationStatus.CONFIRMED, ReservationStatus.COLLECTED}
)


def a_reservation(
    status: ReservationStatus, *, email_verified: bool = True, allocated: int | None = None
) -> ReservationDetail:
    """Return a reservation of two rotary hammers in the given status."""
    held = len(TAGS) if status in HOLDS_UNITS else 0
    allocated_count = held if allocated is None else allocated
    line = ReservationLineDetail(
        model_slug="gbh-2-26-dre-rotary-hammer",
        model_name="GBH 2-26 DRE Rotary Hammer",
        quantity=len(TAGS),
        daily_rate=Decimal("185.00"),
        weekly_rate=Decimal("740.00"),
        deposit_per_unit=Decimal("600.00"),
        line_subtotal_ex_vat=Decimal("1110.00"),
        allocated_count=allocated_count,
        asset_tags=TAGS[:allocated_count],
    )
    return ReservationDetail(
        id=uuid4(),
        reference="TSH-R-26-000124",
        status=status,
        branch_id=BRANCH_ID,
        branch_code="CBD",
        branch_name="Cape Town CBD",
        start_date=date(2026, 3, 9),
        end_date=date(2026, 3, 12),
        lines=(line,),
        subtotal_ex_vat=Decimal("1110.00"),
        discount_percent=Decimal("0.00"),
        vat_amount=Decimal("166.50"),
        estimated_total_inc_vat=Decimal("1276.50"),
        deposit_total=Decimal("1200.00"),
        hold_expires_at=HOLD_RUNS_OUT_AT if status is ReservationStatus.HELD else None,
        confirmed_at=None,
        cancelled_at=None,
        cancellation_reason=None,
        customer_profile_id=uuid4(),
        customer_name="Nomsa Dlamini",
        customer_email_verified=email_verified,
        created_at=NOW,
    )


def offered_to(actor: Actor, detail: ReservationDetail, now: datetime = NOW) -> set[str]:
    """Return the moves the view offers a caller."""
    view = view_for(actor, detail, now)
    flags = {HOLD: view.can_hold, CONFIRM: view.can_confirm, CANCEL: view.can_cancel}
    return {move for move, offered in flags.items() if offered}


class TestTheTableOfStatusesAndCallers:
    """Every status against every kind of caller."""

    @pytest.mark.parametrize("status", list(ReservationStatus))
    @pytest.mark.parametrize(
        "actor", MAY_ACT, ids=["customer", "counter at the branch", "administrator"]
    )
    def test_a_caller_who_may_act_is_offered_exactly_the_legal_moves(
        self, status: ReservationStatus, actor: Actor
    ) -> None:
        assert offered_to(actor, a_reservation(status)) == OFFERED[status]

    @pytest.mark.parametrize("status", list(ReservationStatus))
    def test_counter_staff_of_another_branch_are_offered_nothing_in_any_status(
        self, status: ReservationStatus
    ) -> None:
        assert offered_to(COUNTER_ELSEWHERE, a_reservation(status)) == set()

    def test_the_table_names_every_status(self) -> None:
        assert set(OFFERED) == set(ReservationStatus)


class TestConfirmingNeedsMoreThanTheStatus:
    """The verified address, the hold and the units, each of which can say no."""

    def test_a_customer_whose_address_is_not_verified_is_not_offered_confirm(self) -> None:
        held = a_reservation(ReservationStatus.HELD, email_verified=False)
        assert offered_to(CUSTOMER, held) == {CANCEL}

    @pytest.mark.parametrize("actor", [COUNTER_HERE, ADMINISTRATOR], ids=["counter", "admin"])
    def test_staff_are_offered_confirm_for_a_customer_who_is_not_verified(
        self, actor: Actor
    ) -> None:
        held = a_reservation(ReservationStatus.HELD, email_verified=False)
        assert offered_to(actor, held) == {CONFIRM, CANCEL}

    def test_a_hold_is_offered_for_confirmation_at_the_instant_it_expires(self) -> None:
        held = a_reservation(ReservationStatus.HELD)
        assert offered_to(CUSTOMER, held, HOLD_RUNS_OUT_AT) == {CONFIRM, CANCEL}

    def test_a_hold_that_has_run_out_is_offered_for_nothing(self) -> None:
        held = a_reservation(ReservationStatus.HELD)
        a_second_late = HOLD_RUNS_OUT_AT + timedelta(seconds=1)
        assert offered_to(CUSTOMER, held, a_second_late) == set()
        assert offered_to(ADMINISTRATOR, held, a_second_late) == set()

    def test_a_hold_that_is_short_of_a_unit_is_not_offered_for_confirmation(self) -> None:
        short = a_reservation(ReservationStatus.HELD, allocated=1)
        assert offered_to(CUSTOMER, short) == {CANCEL}

    def test_a_held_reservation_with_no_expiry_set_can_still_be_confirmed(self) -> None:
        """A hold made before holds had an expiry carries none, and never runs out."""
        legacy = replace(a_reservation(ReservationStatus.HELD), hold_expires_at=None)
        assert offered_to(CUSTOMER, legacy, NOW + timedelta(days=30)) == {CONFIRM, CANCEL}


class TestWhoIsShownTheAssetTags:
    """Staff see which units were given. A customer never does (US-07)."""

    def test_a_customer_is_shown_no_tags_and_still_the_count(self) -> None:
        view = view_for(CUSTOMER, a_reservation(ReservationStatus.HELD), NOW)
        (line,) = view.detail.lines
        assert line.asset_tags == ()
        assert line.allocated_count == len(TAGS)

    @pytest.mark.parametrize(
        "actor", [COUNTER_HERE, COUNTER_ELSEWHERE, ADMINISTRATOR], ids=["here", "away", "admin"]
    )
    def test_staff_are_shown_the_tags_at_any_branch(self, actor: Actor) -> None:
        view = view_for(actor, a_reservation(ReservationStatus.CONFIRMED), NOW)
        assert view.detail.lines[0].asset_tags == TAGS

    def test_nothing_else_about_the_reservation_is_changed_for_a_customer(self) -> None:
        detail = a_reservation(ReservationStatus.HELD)
        shown = view_for(CUSTOMER, detail, NOW).detail
        assert replace(shown, lines=detail.lines) == detail


class TestAPageOfReservations:
    """A page is each of its reservations seen by the same caller."""

    def test_every_item_carries_its_own_flags_and_the_page_keeps_its_numbers(self) -> None:
        page = ReservationPage(
            items=(
                a_reservation(ReservationStatus.DRAFT),
                a_reservation(ReservationStatus.CANCELLED),
            ),
            page=2,
            page_size=2,
            total=5,
        )
        shown = page_for(CUSTOMER, page, NOW)
        assert [(view.can_hold, view.can_cancel) for view in shown.items] == [
            (True, True),
            (False, False),
        ]
        assert (shown.page, shown.page_size, shown.total) == (2, 2, 5)
