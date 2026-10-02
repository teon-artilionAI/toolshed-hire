"""The use case that creates a draft reservation, run against ports and nothing else.

A draft is a priced basket. These tests are about what a draft records and
what it leaves alone. It copies the figures of each model onto its line
(BR-20), it is priced by the pricing policy with the customer's trade discount
(BR-21), it writes its audit event in the same transaction (BR-49), and it
holds no unit and queues no notification.

What the use case refuses is in test_create_reservation_refusals.py. The unit
of work is the in memory double from tests/support, and the clock stands still
on the second of March 2026.

The worked example is one rotary hammer for three days at 185.00 a day. That
is 555.00 excluding VAT, 83.25 of VAT at fifteen percent and 638.25 in all,
with a deposit of 600.00 beside it.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.access import RESERVATION_CREATED_ACTION
from app.domain.enums import AccountStatus, ReservationStatus, UserRole
from app.domain.identity import Actor, CustomerProfile
from app.domain.money import Money
from app.domain.policies import FixedRatePricingPolicy
from tests.support.memory import COMMIT, StoreFault
from tests.support.memory_world import FIRST_HIRE, build_memory_world, open_desk

THREE_DAYS_OF_HIRE: Final[Decimal] = Decimal("555.00")
VAT_ON_THREE_DAYS: Final[Decimal] = Decimal("83.25")
TOTAL_FOR_THREE_DAYS: Final[Decimal] = Decimal("638.25")
ONE_DEPOSIT: Final[Decimal] = Decimal("600.00")
TEN_PERCENT: Final[Decimal] = Decimal("10.00")
FIXED_UNIT_CHARGE: Final[Money] = Money.create("100.00")


class TestADraftIsABasket:
    """A draft exists, is priced, and affects nobody else."""

    def test_a_new_reservation_is_a_draft_with_a_reference(self) -> None:
        desk = open_desk(build_memory_world())
        draft = desk.drafted()
        assert draft.detail.status is ReservationStatus.DRAFT
        assert draft.detail.reference == "TSH-R-26-000124"
        assert draft.detail.branch_code == "CBD"
        assert (draft.detail.start_date, draft.detail.end_date) == (
            FIRST_HIRE.start,
            FIRST_HIRE.end,
        )
        assert draft.detail.hire_days == 3

    def test_a_draft_allocates_nothing_and_has_no_hold(self) -> None:
        world = build_memory_world(asset_count=3)
        desk = open_desk(world)
        draft = desk.drafted(world.draft_command(quantity=2))
        assert world.store.committed.allocations == []
        assert draft.detail.lines[0].allocated_count == 0
        assert draft.detail.hold_expires_at is None

    def test_a_draft_queues_no_notification(self) -> None:
        world = build_memory_world()
        open_desk(world).drafted()
        assert world.store.committed.notifications == {}

    def test_a_draft_can_be_made_for_more_units_than_are_free(self) -> None:
        """Nothing is held, so nothing is checked against the fleet until the hold."""
        world = build_memory_world(asset_count=1)
        draft = open_desk(world).drafted(world.draft_command(quantity=5))
        assert draft.detail.lines[0].quantity == 5

    def test_the_draft_is_committed_exactly_once(self) -> None:
        world = build_memory_world()
        open_desk(world).drafted()
        assert world.store.journal == [COMMIT]
        assert len(world.store.committed.reservations) == 1

    def test_the_draft_belongs_to_the_customers_profile_and_names_its_creator(self) -> None:
        world = build_memory_world()
        draft = open_desk(world).drafted()
        stored = world.stored(draft.detail.id)
        assert stored.customer_profile_id == world.profile.id
        assert stored.created_by_user_id == world.customer_account_id
        assert draft.detail.customer_name == "Nomsa Dlamini"


class TestTheFiguresAreFixedWhenTheLineIsAdded:
    """The snapshots and the totals, which a later catalogue change never alters."""

    def test_the_line_copies_the_five_figures_of_the_model(self) -> None:
        world = build_memory_world()
        draft = open_desk(world).drafted()
        (line,) = world.stored(draft.detail.id).lines
        model = world.product_model
        assert line.daily_rate_snapshot == model.daily_rate
        assert line.weekly_rate_snapshot == model.weekly_rate
        assert line.deposit_snapshot == model.deposit_amount
        assert line.late_fee_per_day_snapshot == model.late_fee_per_day
        assert line.replacement_value_snapshot == model.replacement_value

    def test_the_totals_are_the_figures_of_the_pricing_policy(self) -> None:
        draft = open_desk(build_memory_world()).drafted()
        detail = draft.detail
        assert detail.lines[0].line_subtotal_ex_vat == THREE_DAYS_OF_HIRE
        assert detail.subtotal_ex_vat == THREE_DAYS_OF_HIRE
        assert detail.vat_amount == VAT_ON_THREE_DAYS
        assert detail.estimated_total_inc_vat == TOTAL_FOR_THREE_DAYS
        assert detail.deposit_total == ONE_DEPOSIT
        assert detail.discount_percent == Decimal("0.00")

    def test_two_units_double_the_hire_and_the_deposit(self) -> None:
        world = build_memory_world(asset_count=2)
        detail = open_desk(world).drafted(world.draft_command(quantity=2)).detail
        assert detail.subtotal_ex_vat == Decimal("1110.00")
        assert detail.vat_amount == Decimal("166.50")
        assert detail.estimated_total_inc_vat == Decimal("1276.50")
        assert detail.deposit_total == Decimal("1200.00")

    def test_the_trade_discount_of_the_customer_is_applied_and_recorded(self) -> None:
        """555.00 less ten percent is 499.50, and the VAT on that is 74.93."""
        world = build_memory_world(trade_discount_percent=TEN_PERCENT)
        detail = open_desk(world).drafted().detail
        assert detail.discount_percent == TEN_PERCENT
        assert detail.subtotal_ex_vat == Decimal("499.50")
        assert detail.vat_amount == Decimal("74.93")
        assert detail.estimated_total_inc_vat == Decimal("574.43")
        assert detail.deposit_total == ONE_DEPOSIT

    def test_the_subtotal_and_the_vat_add_up_to_the_total(self) -> None:
        world = build_memory_world(trade_discount_percent=TEN_PERCENT, asset_count=3)
        detail = open_desk(world).drafted(world.draft_command(quantity=3)).detail
        assert detail.subtotal_ex_vat + detail.vat_amount == detail.estimated_total_inc_vat

    def test_the_price_comes_from_whichever_policy_the_use_case_was_given(self) -> None:
        world = build_memory_world()
        desk = open_desk(world, pricing=FixedRatePricingPolicy(FIXED_UNIT_CHARGE))
        detail = desk.drafted(world.draft_command(quantity=2)).detail
        assert detail.subtotal_ex_vat == Decimal("200.00")
        assert detail.estimated_total_inc_vat == Decimal("230.00")

    def test_a_price_change_after_the_draft_leaves_its_figures_alone(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        world.store.product_models[world.product_model.id] = replace(
            world.product_model, daily_rate=Decimal("999.00"), deposit_amount=Decimal("9.00")
        )
        again = desk.reads.one(desk.command_for(draft))
        assert again.detail.lines[0].daily_rate == Decimal("185.00")
        assert again.detail.estimated_total_inc_vat == TOTAL_FOR_THREE_DAYS
        assert again.detail.deposit_total == ONE_DEPOSIT


class TestTheAuditEvent:
    """Every creation writes one event, in the same transaction (BR-49)."""

    def test_the_event_names_the_reservation_the_actor_and_what_was_asked_for(self) -> None:
        world = build_memory_world()
        draft = open_desk(world).drafted()
        (event,) = world.store.committed.audit_events
        assert event.action == RESERVATION_CREATED_ACTION
        assert event.entity_type == "reservation"
        assert event.entity_id == draft.detail.id
        assert event.actor_user_id == world.customer_account_id
        assert event.actor_role is UserRole.CUSTOMER
        assert event.before_state is None
        assert event.after_state is not None
        assert event.after_state["status"] == "DRAFT"
        assert event.after_state["reference"] == draft.detail.reference
        assert event.after_state["model_skus"] == [world.product_model.sku]
        assert event.after_state["estimated_total_inc_vat"] == "638.25"

    def test_a_draft_whose_audit_event_cannot_be_written_does_not_exist(self) -> None:
        world = build_memory_world()
        world.store.fail_audit = True
        with pytest.raises(StoreFault):
            open_desk(world).drafted()
        assert world.store.committed.reservations == []
        assert world.store.journal == []


class TestStaffBookForANamedCustomer:
    """Counter staff and administrators create a draft for a customer profile."""

    def test_a_counter_assistant_books_for_the_customer_at_their_own_branch(self) -> None:
        world = build_memory_world()
        assistant = world.assistant()
        draft = open_desk(world).drafted(
            world.draft_command(actor=assistant, customer_profile_id=world.profile.id)
        )
        stored = world.stored(draft.detail.id)
        assert stored.customer_profile_id == world.profile.id
        assert stored.created_by_user_id == assistant.user_id
        (event,) = world.store.committed.audit_events
        assert event.actor_role is UserRole.COUNTER_STAFF

    def test_an_administrator_books_for_a_walk_in_who_has_no_account(self) -> None:
        world = build_memory_world()
        walk_in = CustomerProfile(
            id=uuid4(),
            user_account_id=None,
            display_name="Thabo Mokoena",
            account_status=AccountStatus.ACTIVE,
            email=None,
        )
        world.store.walk_ins.append(walk_in)
        administrator = Actor(user_id=uuid4(), role=UserRole.ADMIN)
        draft = open_desk(world).drafted(
            world.draft_command(actor=administrator, customer_profile_id=walk_in.id)
        )
        assert draft.detail.customer_name == "Thabo Mokoena"
        assert world.stored(draft.detail.id).customer_profile_id == walk_in.id

    def test_the_named_customers_discount_is_the_one_applied(self) -> None:
        world = build_memory_world(trade_discount_percent=TEN_PERCENT)
        draft = open_desk(world).drafted(
            world.draft_command(actor=world.assistant(), customer_profile_id=world.profile.id)
        )
        assert draft.detail.discount_percent == TEN_PERCENT
