"""What one caller is shown of a rental and of a checkout, with no database anywhere.

The read models are built by hand and handed to the two view builders of the
hire module. These pin that a customer is never shown a tag, who may record a
return, what the deposit waits on, what the late fee policy says a unit still
out would owe today, the order the refusals of a checkout are tried in, and
the bounds of the two keys and of a customer search.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.application.hire.read_models import (
    ChargeDetail,
    CheckoutCustomer,
    CheckoutDetail,
    CheckoutUnit,
    RentalDetail,
    RentalItemDetail,
    RentalKey,
)
from app.application.hire.views import checkout_view_for, rental_view_for
from app.application.identity.customer_directory import CustomerSearch
from app.domain.checkout import ALREADY_CHECKED_OUT_MESSAGE
from app.domain.enums import (
    AccountStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    IdDocType,
    RentalStatus,
    ReservationStatus,
    UserRole,
)
from app.domain.identity import BRANCH_SCOPE_MESSAGE, Actor
from app.domain.policies import StandardLateFeePolicy
from app.domain.rental import DamageAssessment, SettlementWait
from app.domain.states.guards import TOO_EARLY_TO_COLLECT_MESSAGE

BRANCH: Final[UUID] = uuid4()
NOW: Final[datetime] = datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
FIRST_DAY: Final[date] = date(2026, 3, 9)
DAY_BEFORE: Final[date] = date(2026, 3, 8)
TAG: Final[str] = "TSH-DR-0042"
DUE_BACK_ON: Final[date] = date(2026, 3, 12)
POLICY: Final[StandardLateFeePolicy] = StandardLateFeePolicy()


def an_actor(role: UserRole, *, at_the_branch: bool = True) -> Actor:
    """Return an actor of a role, at the branch or at another one when it is counter staff."""
    if role is not UserRole.COUNTER_STAFF:
        return Actor(user_id=uuid4(), role=role)
    return Actor(user_id=uuid4(), role=role, branch_id=BRANCH if at_the_branch else uuid4())


def an_item(*, returned_at: datetime | None = None) -> RentalItemDetail:
    """Return one item of a rental, out unless a return time is given."""
    return RentalItemDetail(
        id=uuid4(),
        asset_tag=TAG,
        model_name="GBH 2-26 DRE Rotary Hammer",
        model_slug="gbh-2-26-dre-rotary-hammer",
        condition_out=ConditionGrade.A,
        condition_in=None,
        hour_meter_out=None,
        hour_meter_in=None,
        accessories_out=None,
        accessories_in=None,
        returned_at=returned_at,
        days_late=0,
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("6500.00"),
    )


def a_rental(
    *items: RentalItemDetail, status: RentalStatus = RentalStatus.OPEN
) -> RentalDetail:
    """Return a rental at the branch with the given items and one deposit charge."""
    rental_id = uuid4()
    return RentalDetail(
        id=rental_id,
        reference="TSH-H-26-000099",
        status=status,
        reservation_id=uuid4(),
        reservation_reference="TSH-R-26-000124",
        branch_id=BRANCH,
        branch_code="CBD",
        branch_name="Cape Town CBD",
        customer_profile_id=uuid4(),
        customer_name="Nomsa Dlamini",
        customer_phone="082 441 7719",
        start_date=FIRST_DAY,
        due_back_on=DUE_BACK_ON,
        checked_out_at=NOW,
        returned_at=None,
        items=items or (an_item(),),
        charges=(
            ChargeDetail(
                id=uuid4(),
                charge_type=ChargeType.DEPOSIT_HOLD,
                description="Refundable deposit held at collection",
                amount_ex_vat=Decimal("1200.00"),
                vat_rate=Decimal("0.00"),
                vat_amount=Decimal("0.00"),
                amount_inc_vat=Decimal("1200.00"),
                status=ChargeStatus.SETTLED,
                raised_at=NOW,
                rental_item_id=None,
            ),
        ),
        deposit_held=Decimal("1200.00"),
        deposit_withheld=Decimal("0.00"),
        deposit_refunded=Decimal("0.00"),
        balance_due=Decimal("0.00"),
        settled_at=None,
        agreement_signed=True,
    )


def a_checkout(
    *, status: ReservationStatus = ReservationStatus.CONFIRMED, rental_id: UUID | None = None
) -> CheckoutDetail:
    """Return a reservation at the branch as the counter is about to check it out."""
    unit = CheckoutUnit(
        allocation_id=uuid4(),
        asset_tag=TAG,
        model_name="GBH 2-26 DRE Rotary Hammer",
        model_slug="gbh-2-26-dre-rotary-hammer",
        condition_grade=ConditionGrade.A,
        hour_meter=None,
        deposit_per_unit=Decimal("1200.00"),
    )
    return CheckoutDetail(
        reservation_id=uuid4(),
        reference="TSH-R-26-000124",
        status=status,
        branch_id=BRANCH,
        branch_code="CBD",
        branch_name="Cape Town CBD",
        customer=CheckoutCustomer(
            id=uuid4(),
            display_name="Nomsa Dlamini",
            phone="082 441 7719",
            id_document_type=IdDocType.SA_ID,
            id_document_last4="4189",
            account_status=AccountStatus.ACTIVE,
        ),
        start_date=FIRST_DAY,
        end_date=date(2026, 3, 12),
        units=(unit, replace(unit, allocation_id=uuid4(), asset_tag="TSH-DR-0043")),
        hire_total_inc_vat=Decimal("966.00"),
        rental_id=rental_id,
    )


class TestARentalAsACallerSeesIt:
    """Tags for staff only, and what the counter may do next."""

    def test_staff_see_the_tag_and_a_customer_does_not(self) -> None:
        rental = a_rental()
        staff_view = rental_view_for(an_actor(UserRole.ADMIN), rental, FIRST_DAY, POLICY)
        customer_view = rental_view_for(an_actor(UserRole.CUSTOMER), rental, FIRST_DAY, POLICY)
        assert staff_view.items[0].item.asset_tag == TAG
        assert customer_view.items[0].item.asset_tag is None
        assert staff_view.items[0].item.replacement_value == Decimal("6500.00")
        assert customer_view.items[0].item.replacement_value is None
        assert rental.items[0].asset_tag == TAG, "The stored rental was changed."

    @pytest.mark.parametrize(
        ("actor", "can_return"),
        [
            (an_actor(UserRole.COUNTER_STAFF), True),
            (an_actor(UserRole.COUNTER_STAFF, at_the_branch=False), False),
            (an_actor(UserRole.ADMIN), True),
            (an_actor(UserRole.CUSTOMER), False),
        ],
    )
    def test_only_staff_of_the_branch_or_an_administrator_may_record_a_return(
        self, actor: Actor, can_return: bool
    ) -> None:
        assert rental_view_for(actor, a_rental(), FIRST_DAY, POLICY).can_return is can_return

    def test_nothing_is_returned_once_everything_is_back_or_the_hire_is_settled(self) -> None:
        administrator = an_actor(UserRole.ADMIN)
        back = a_rental(an_item(returned_at=NOW))
        settled = a_rental(status=RentalStatus.SETTLED)
        assert rental_view_for(administrator, back, FIRST_DAY, POLICY).can_return is False
        assert rental_view_for(administrator, settled, FIRST_DAY, POLICY).can_return is False

    def test_the_deposit_waits_for_the_units_that_are_still_out(self) -> None:
        administrator = an_actor(UserRole.ADMIN)
        partly = a_rental(an_item(), an_item(returned_at=NOW))
        back = a_rental(an_item(returned_at=NOW))
        assert rental_view_for(administrator, partly, FIRST_DAY, POLICY).settlement_waiting_on is (
            SettlementWait.ITEMS_OUT
        )
        assert rental_view_for(administrator, back, FIRST_DAY, POLICY).settlement_waiting_on is None

    def test_a_balance_left_after_settlement_waits_for_its_payment(self) -> None:
        owing = replace(
            a_rental(an_item(returned_at=NOW), status=RentalStatus.RETURNED),
            balance_due=Decimal("300.00"),
        )
        settled = replace(owing, status=RentalStatus.SETTLED, balance_due=Decimal("0.00"))
        administrator = an_actor(UserRole.ADMIN)
        assert rental_view_for(administrator, owing, FIRST_DAY, POLICY).settlement_waiting_on is (
            SettlementWait.BALANCE_PAYMENT
        )
        assert rental_view_for(administrator, settled, FIRST_DAY, POLICY).settlement_waiting_on is (
            None
        )

    @pytest.mark.parametrize(
        ("today", "days_late", "fee"),
        [
            (DUE_BACK_ON, 0, Decimal("0.00")),
            (date(2026, 3, 14), 2, Decimal("240.00")),
            (date(2026, 4, 30), 49, Decimal("1680.00")),
        ],
    )
    def test_a_unit_still_out_shows_what_the_policy_would_charge_today(
        self, today: date, days_late: int, fee: Decimal
    ) -> None:
        (item,) = rental_view_for(an_actor(UserRole.ADMIN), a_rental(), today, POLICY).items
        assert (item.days_late_today, item.late_fee_today) == (days_late, fee)
        assert item.damage_assessment is DamageAssessment.NOT_NEEDED

    def test_a_unit_that_is_back_accrues_nothing_more(self) -> None:
        back = a_rental(an_item(returned_at=NOW))
        (item,) = rental_view_for(an_actor(UserRole.ADMIN), back, date(2026, 4, 30), POLICY).items
        assert (item.days_late_today, item.late_fee_today) == (0, Decimal("0.00"))


class TestACheckoutAsTheCounterSeesIt:
    """Whether the counter may hand over now, and why not in the checkout's own words."""

    def test_a_confirmed_reservation_on_its_first_day_may_be_checked_out(self) -> None:
        view = checkout_view_for(an_actor(UserRole.COUNTER_STAFF), a_checkout(), FIRST_DAY)
        assert (view.can_check_out, view.refusal) == (True, None)
        assert view.deposit_total == Decimal("2400.00")

    @pytest.mark.parametrize(
        ("actor", "detail", "today", "refusal"),
        [
            (
                an_actor(UserRole.COUNTER_STAFF, at_the_branch=False),
                a_checkout(rental_id=uuid4(), status=ReservationStatus.COLLECTED),
                FIRST_DAY,
                BRANCH_SCOPE_MESSAGE,
            ),
            (
                an_actor(UserRole.ADMIN),
                a_checkout(rental_id=uuid4(), status=ReservationStatus.COLLECTED),
                FIRST_DAY,
                ALREADY_CHECKED_OUT_MESSAGE,
            ),
            (
                an_actor(UserRole.ADMIN),
                a_checkout(status=ReservationStatus.HELD),
                DAY_BEFORE,
                "This reservation is on hold, so it cannot be collected.",
            ),
            (an_actor(UserRole.ADMIN), a_checkout(), DAY_BEFORE, TOO_EARLY_TO_COLLECT_MESSAGE),
        ],
        ids=["the branch first", "then a rental", "then the status", "then the date"],
    )
    def test_the_refusals_are_tried_in_the_order_the_checkout_tries_them(
        self, actor: Actor, detail: CheckoutDetail, today: date, refusal: str
    ) -> None:
        view = checkout_view_for(actor, detail, today)
        assert (view.can_check_out, view.refusal) == (False, refusal)

    def test_the_hire_is_counted_in_days(self) -> None:
        assert a_checkout().hire_days == 3


class TestTheKeysAndTheBounds:
    """A rental named by key or reference, and a customer search that cannot ask for all."""

    def test_a_rental_is_named_by_its_key_or_by_its_reference_in_upper_case(self) -> None:
        key = uuid4()
        assert RentalKey.parse(f" {key} ") == RentalKey(rental_id=key)
        assert RentalKey.parse("tsh-h-26-000099") == RentalKey(reference="TSH-H-26-000099")
        assert RentalKey.parse("x" * 40).reference == "X" * 16
        assert str(RentalKey.of(key)) == str(key)
        assert str(RentalKey.parse("tsh-h-26-000099")) == "TSH-H-26-000099"

    @pytest.mark.parametrize(
        "bounds",
        [
            {"text": "T"},
            {"text": "x" * 81},
            {"text": "Thandi", "page": 0},
            {"text": "Thandi", "page": 10_001},
            {"text": "Thandi", "page_size": 0},
            {"text": "Thandi", "page_size": 51},
        ],
    )
    def test_a_customer_search_out_of_bounds_cannot_be_built(
        self, bounds: dict[str, object]
    ) -> None:
        with pytest.raises(ValueError, match="Attempted to"):
            CustomerSearch(**bounds)

    def test_a_customer_search_knows_how_many_come_before_its_page(self) -> None:
        assert CustomerSearch(text="Thandi", page=3, page_size=20).offset == 40
