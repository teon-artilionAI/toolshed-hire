"""What one caller is shown of a rental or of a checkout, and what they may do next.

A rental is answered as a `RentalView`. It is the stored rental, less anything
the caller may not see, with what the late fee would be today for each unit
still out, whether a returned unit waits for its damage to be assessed, what
the deposit is waiting on, and whether the caller may record a return right
now. Those answers are worked out in `app.application.hire.progress`, the late
fee by the late fee policy the caller hands in. A page of rentals is a
`RentalViewPage`, each rental on it built the same way.

A checkout is answered as a `CheckoutView`, which says whether the caller may
hand the equipment over right now and, when not, why, in the sentence the
checkout itself would answer with. The refusals are tried in the order the
checkout tries them. The branch comes first, then a rental that already
exists, then the status and the date.

A customer is never shown an asset tag (US-07). Counter staff and
administrators are, because they hand the units over.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from app.application.booking.access import is_staff
from app.application.hire.list_models import RentalPage
from app.application.hire.progress import (
    damage_assessment_of,
    late_fee_if_returned_today,
    settlement_waiting_on,
)
from app.application.hire.read_models import CheckoutDetail, RentalDetail, RentalItemDetail
from app.domain.checkout import ALREADY_CHECKED_OUT_MESSAGE, collection_refusal
from app.domain.checkout_charges import deposit_to_hold
from app.domain.enums import RentalStatus, UserRole
from app.domain.identity import BRANCH_SCOPE_MESSAGE, Actor, within_branch_scope
from app.domain.policies.late_fee import LateFeePolicy
from app.domain.rental import DamageAssessment, SettlementWait


@dataclass(frozen=True, slots=True)
class RentalItemView:
    """One unit of a rental as one caller sees it.

    Attributes:
        item: The unit as it is stored, with its tag removed for a customer.
        days_late_today: The whole days it would be late if it came back today.
        late_fee_today: The late fee it would carry if it came back today.
        damage_assessment: Whether it waits for its damage to be assessed.

    """

    item: RentalItemDetail
    days_late_today: int
    late_fee_today: Decimal
    damage_assessment: DamageAssessment


@dataclass(frozen=True, slots=True)
class RentalView:
    """One rental as one caller sees it.

    Attributes:
        detail: The rental as it is stored.
        items: Its units, as this caller sees them.
        can_return: True when the caller may record a return right now.
        settlement_waiting_on: What the deposit waits on, or None.

    """

    detail: RentalDetail
    items: tuple[RentalItemView, ...]
    can_return: bool
    settlement_waiting_on: SettlementWait | None


@dataclass(frozen=True, slots=True)
class CheckoutView:
    """A reservation as the counter is about to hand it over.

    Attributes:
        detail: The reservation and the units it holds.
        deposit_total: The deposit the checkout would take (BR-27).
        can_check_out: True when the caller may check it out right now.
        refusal: Why not, in a sentence, when `can_check_out` is False.

    """

    detail: CheckoutDetail
    deposit_total: Decimal
    can_check_out: bool
    refusal: str | None


@dataclass(frozen=True, slots=True)
class RentalViewPage:
    """One page of rentals as one caller sees them.

    Attributes:
        items: The rentals on the page.
        page: The page this is, counted from one.
        page_size: How many rentals a page holds.
        total: How many rentals match across every page.

    """

    items: tuple[RentalView, ...]
    page: int
    page_size: int
    total: int


def rental_view_for(
    actor: Actor, detail: RentalDetail, today: date, policy: LateFeePolicy
) -> RentalView:
    """Build what one caller is shown of a rental they may read.

    Args:
        actor: Who is asking, with the role and the branch they hold.
        detail: The rental as it is stored.
        today: The current business day, from the clock.
        policy: The late fee policy, which says what each unit still out
            would owe if it came back today.

    """
    items = tuple(
        _item_view(actor, item, detail.due_back_on, today, policy) for item in detail.items
    )
    return RentalView(
        detail=detail,
        items=items,
        can_return=(
            is_staff(actor)
            and within_branch_scope(actor, detail.branch_id)
            and detail.status is not RentalStatus.SETTLED
            and any(item.is_out() for item in detail.items)
        ),
        settlement_waiting_on=settlement_waiting_on(detail),
    )


def rental_page_for(
    actor: Actor, page: RentalPage, today: date, policy: LateFeePolicy
) -> RentalViewPage:
    """Build what one caller is shown of a page of rentals."""
    return RentalViewPage(
        items=tuple(rental_view_for(actor, detail, today, policy) for detail in page.items),
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


def checkout_view_for(actor: Actor, detail: CheckoutDetail, today: date) -> CheckoutView:
    """Build what the counter is shown of a reservation it is about to hand over.

    Args:
        actor: Who is asking, with the role and the branch they hold.
        detail: The reservation and the units it holds.
        today: The current business day, from the clock.

    """
    refusal = _checkout_refusal(actor, detail, today)
    return CheckoutView(
        detail=detail,
        deposit_total=deposit_to_hold(unit.deposit_per_unit for unit in detail.units).amount,
        can_check_out=refusal is None,
        refusal=refusal,
    )


def _checkout_refusal(actor: Actor, detail: CheckoutDetail, today: date) -> str | None:
    """Return the sentence a checkout by this caller would be refused with today, or None."""
    if not within_branch_scope(actor, detail.branch_id):
        return BRANCH_SCOPE_MESSAGE
    if detail.rental_id is not None:
        return ALREADY_CHECKED_OUT_MESSAGE
    return collection_refusal(detail.status, detail.start_date, today)


def _item_view(
    actor: Actor, item: RentalItemDetail, due_back_on: date, today: date, policy: LateFeePolicy
) -> RentalItemView:
    """Return one unit as the caller sees it, without its tag for a customer (US-07)."""
    late = late_fee_if_returned_today(item, due_back_on, today, policy)
    shown = replace(item, asset_tag=None) if actor.role is UserRole.CUSTOMER else item
    return RentalItemView(
        item=shown,
        days_late_today=late.days_late,
        late_fee_today=late.amount,
        damage_assessment=damage_assessment_of(item),
    )
