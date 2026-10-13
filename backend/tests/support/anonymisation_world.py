"""A customer with a history, for the tests of anonymisation (#113).

A customer with an account hires one unit, the hire comes back and is settled,
and on the way someone types about them into every free text column the
personal data map lists. A unit came back damaged, a charge was waived, a
confirmation could not be sent and the account signed in twice. A test asks
for the history ended on a day of its choosing, so the monthly job's two years
can be tested on rows back dated past them, and for a booking or a hire left
open, so the refusals can be.

Like the other factories this flushes and never commits, so the test owns the
transaction.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from ipaddress import IPv4Address
from typing import Final
from uuid import uuid4

from sqlmodel import col, select

from app.domain.enums import (
    ChargeStatus,
    ChargeType,
    DamageSeverity,
    DamageStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RentalStatus,
    ReservationStatus,
    UserRole,
)
from app.infrastructure.models import (
    Charge,
    DamageReport,
    Notification,
    RefreshSession,
    Rental,
    RentalItem,
    UserAccount,
)
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.factories import Factory
from tests.support.hire_factories import Booked, HireFactory, hire_from

# What was typed about the customer, which an anonymisation must not leave.
TYPED_NOTE: Final[str] = "Nomsa rang from 082 441 7719 to say she would be late."
TYPED_REASON: Final[str] = "Nomsa Dlamini moved to Durban."
TYPED_DAMAGE: Final[str] = "Nomsa dropped the breaker off her bakkie in Salt River."
TYPED_WAIVER: Final[str] = "Waived for Nomsa Dlamini, a regular since 2020."
PROVIDER_ERROR: Final[str] = "Mailbox nomsa.dlamini@example.co.za is full."
USER_AGENT: Final[str] = "Mozilla/5.0 (Nomsa's phone)"
CLIENT_ADDRESS: Final[IPv4Address] = IPv4Address("196.25.1.200")
# When the history ends when a test does not say.
RECENTLY: Final[datetime] = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
# How long before its end the history began.
HISTORY_LENGTH: Final[timedelta] = timedelta(days=30)
SESSION_LIFETIME: Final[timedelta] = timedelta(days=14)
WAIVED_AMOUNT: Final[Decimal] = Decimal("150.00")
NO_VAT: Final[Decimal] = Decimal("0")
HASH_WIDTH: Final[int] = 64

_numbers: Final[itertools.count[int]] = itertools.count(1)


@dataclass(frozen=True, slots=True)
class CustomerHistory:
    """A customer, their settled hire and everything typed about them on the way."""

    world: BookingWorld
    owner: UserAccount
    booked: Booked
    rental: Rental
    item: RentalItem
    report: DamageReport
    waived: Charge
    notification: Notification
    sessions: list[RefreshSession]


def build_customer_history(
    factory: Factory,
    *,
    ended_at: datetime = RECENTLY,
    rental_status: RentalStatus = RentalStatus.SETTLED,
    balance_due: Decimal = Decimal("0"),
    with_owner: UserAccount | None = None,
) -> CustomerHistory:
    """Build a customer whose hire ended at `ended_at`, with notes typed about them.

    The profile, the account, the booking and the sessions are dated
    `HISTORY_LENGTH` before the end, and the account last signed in then.

    Args:
        factory: The factory bound to the session under test.
        ended_at: When the hire came back and was settled.
        rental_status: The status the hire is left in.
        balance_due: What the hire still owes.
        with_owner: The administrator who served the customer, or None to
            make one.

    """
    session = factory.session
    began_at = ended_at - HISTORY_LENGTH
    world = build_booking_world(factory)
    owner = with_owner or factory.user(role=UserRole.ADMIN)
    hires = HireFactory(factory)
    booked = hires.booking(
        profile=world.profile,
        created_by=owner,
        branch=world.branch,
        model=world.product_model,
        units=world.assets,
        period=hire_from(date(began_at.year, began_at.month, began_at.day)),
        status=ReservationStatus.RETURNED,
    )
    booked.reservation.notes = TYPED_NOTE
    booked.reservation.cancellation_reason = TYPED_REASON
    rental = hires.rental(
        booked, checked_out_by=owner, units_back=len(world.assets), status=rental_status
    )
    rental.returned_at = ended_at
    rental.balance_due = balance_due
    rental.settled_at = ended_at if rental_status is RentalStatus.SETTLED else None
    item = _first_item(factory, rental)
    item.notes = TYPED_NOTE
    report = _damage_report(factory, item, owner, ended_at)
    waived = _waived_charge(factory, rental, owner, ended_at)
    notification = _failed_confirmation(factory, world, booked, began_at)
    sessions = [_session(factory, world.customer, began_at) for _ in range(2)]
    world.customer.last_login_at = began_at
    world.customer.created_at = began_at
    world.profile.created_at = began_at
    booked.reservation.created_at = began_at
    session.add_all([world.customer, world.profile, booked.reservation, rental, item])
    session.flush()
    return CustomerHistory(
        world=world,
        owner=owner,
        booked=booked,
        rental=rental,
        item=item,
        report=report,
        waived=waived,
        notification=notification,
        sessions=sessions,
    )


def _first_item(factory: Factory, rental: Rental) -> RentalItem:
    """Return the one unit on a hire."""
    return factory.session.exec(
        select(RentalItem).where(col(RentalItem.rental_id) == rental.id)
    ).one()


def _damage_report(
    factory: Factory, item: RentalItem, owner: UserAccount, at: datetime
) -> DamageReport:
    """Record that the unit came back damaged, with a description that names the customer."""
    report = DamageReport(
        reference=f"TSH-D-26-{next(_numbers):06d}",
        asset_id=item.asset_id,
        rental_item_id=item.id,
        severity=DamageSeverity.MINOR,
        status=DamageStatus.RESOLVED,
        description=TYPED_DAMAGE,
        repair_estimate=WAIVED_AMOUNT,
        actual_repair_cost=WAIVED_AMOUNT,
        chargeable_to_customer=False,
        reported_by_user_id=owner.id,
        reported_at=at,
        resolved_at=at,
        resolution_notes=TYPED_NOTE,
    )
    factory.session.add(report)
    factory.session.flush()
    return report


def _waived_charge(
    factory: Factory, rental: Rental, owner: UserAccount, at: datetime
) -> Charge:
    """Waive a cleaning charge on the hire, with a reason that names the customer."""
    charge = Charge(
        rental_id=rental.id,
        charge_type=ChargeType.CLEANING,
        description="Cleaning of returned equipment",
        amount_ex_vat=WAIVED_AMOUNT,
        vat_rate=NO_VAT,
        vat_amount=NO_VAT,
        amount_inc_vat=WAIVED_AMOUNT,
        status=ChargeStatus.WAIVED,
        raised_at=at,
        raised_by_user_id=owner.id,
        waiver_reason=TYPED_WAIVER,
    )
    factory.session.add(charge)
    factory.session.flush()
    return charge


def _failed_confirmation(
    factory: Factory, world: BookingWorld, booked: Booked, at: datetime
) -> Notification:
    """Record a confirmation to the customer that could not be sent."""
    notification = Notification(
        reservation_id=booked.reservation.id,
        notification_type=NotificationType.BOOKING_CONFIRMATION,
        channel=NotificationChannel.EMAIL,
        recipient_email=world.customer.email,
        subject=f"Your Toolshed Hire booking {booked.reservation.reference}",
        status=NotificationStatus.FAILED,
        provider="resend",
        attempts=1,
        last_error=PROVIDER_ERROR,
        queued_at=at,
    )
    factory.session.add(notification)
    factory.session.flush()
    return notification


def _session(factory: Factory, account: UserAccount, at: datetime) -> RefreshSession:
    """Record a sign in of the account, from the customer's phone, still live."""
    row = RefreshSession(
        user_account_id=account.id,
        family_id=uuid4(),
        token_hash=f"{next(_numbers):0{HASH_WIDTH}x}",
        issued_at=at,
        expires_at=at + SESSION_LIFETIME,
        user_agent=USER_AGENT,
        ip_address=CLIENT_ADDRESS,
    )
    factory.session.add(row)
    factory.session.flush()
    return row


__all__ = [
    "CLIENT_ADDRESS",
    "PROVIDER_ERROR",
    "TYPED_DAMAGE",
    "TYPED_NOTE",
    "TYPED_REASON",
    "TYPED_WAIVER",
    "USER_AGENT",
    "CustomerHistory",
    "build_customer_history",
]
