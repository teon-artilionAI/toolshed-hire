"""What the booking module is asked with and what a read of it hands back.

A read returns small frozen dataclasses and never a table row, the same way
the catalogue reads do. `ReservationDetail` is one reservation as it is stored,
with its lines and the units held for each. What a particular caller is shown
of it, and what they may do to it next, is worked out from this in
`app.application.booking.views`.

Money stays `Decimal` all the way to the HTTP boundary, which writes it as a
string with two decimals (BR-22).

A reservation is named by its key or by its reference. `ReservationKey` reads
whichever one a caller typed, so a customer can quote the reference from their
confirmation and a screen can use the key it was given.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.domain.enums import ReservationStatus

MINIMUM_PAGE_SIZE: Final[int] = 1
MAXIMUM_PAGE_SIZE: Final[int] = 50
DEFAULT_PAGE_SIZE: Final[int] = 20
# The width of the reference column. Nothing longer can be a reference.
REFERENCE_MAX_LENGTH: Final[int] = 16


@dataclass(frozen=True, slots=True)
class ReservationKey:
    """How a caller names one reservation, by its key or by its reference.

    Attributes:
        reservation_id: The key, when the caller gave a UUID.
        reference: The reference, in upper case, when the caller gave anything else.

    """

    reservation_id: UUID | None = None
    reference: str | None = None

    @classmethod
    def parse(cls, text: str) -> ReservationKey:
        """Read what a caller typed as a key when it is one, and as a reference otherwise."""
        candidate = text.strip()
        try:
            return cls(reservation_id=UUID(candidate))
        except ValueError:
            return cls(reference=candidate.upper()[:REFERENCE_MAX_LENGTH])

    @classmethod
    def of(cls, reservation_id: UUID) -> ReservationKey:
        """Return the key that names a reservation by its id."""
        return cls(reservation_id=reservation_id)

    def __str__(self) -> str:
        """Return the key or the reference, whichever the caller gave."""
        return str(self.reservation_id) if self.reservation_id is not None else str(self.reference)


@dataclass(frozen=True, slots=True)
class ReservationLineDetail:
    """One line of a reservation, as it is stored.

    Attributes:
        model_slug: The slug of the model the line hires.
        model_name: Its display name.
        quantity: How many units.
        daily_rate: The daily rate copied onto the line (BR-20).
        weekly_rate: The weekly rate copied onto the line.
        deposit_per_unit: The deposit for one unit, copied onto the line.
        line_subtotal_ex_vat: The hire of the line after the discount.
        allocated_count: How many units are held for the line right now.
        asset_tags: The tags of those units, in tag order.

    """

    model_slug: str
    model_name: str
    quantity: int
    daily_rate: Decimal
    weekly_rate: Decimal
    deposit_per_unit: Decimal
    line_subtotal_ex_vat: Decimal
    allocated_count: int
    asset_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReservationDetail:
    """One reservation with its lines, as it is stored.

    Attributes:
        id: The reservation key.
        reference: The reference a customer quotes, for example TSH-R-26-000124.
        status: Where the booking stands.
        branch_id: The collection branch.
        branch_code: Its short code.
        branch_name: Its display name.
        start_date: The first day of the hire.
        end_date: The day the equipment comes back, which is not charged.
        lines: The lines, in position order.
        subtotal_ex_vat: The hire of every line after the discount.
        discount_percent: The trade discount the reservation was priced with.
        vat_amount: The VAT on the subtotal.
        estimated_total_inc_vat: The subtotal and the VAT together.
        deposit_total: The deposit across every unit.
        hold_expires_at: When the hold lapses, while the booking is held.
        confirmed_at: When it was confirmed.
        cancelled_at: When it was cancelled.
        cancellation_reason: Why, when a reason was given.
        customer_profile_id: The customer the booking belongs to.
        customer_name: The name staff see for that customer.
        customer_email_verified: True when that customer has proved the
            address of their account (BR-47).
        created_at: When the booking was created.

    """

    id: UUID
    reference: str
    status: ReservationStatus
    branch_id: UUID
    branch_code: str
    branch_name: str
    start_date: date
    end_date: date
    lines: tuple[ReservationLineDetail, ...]
    subtotal_ex_vat: Decimal
    discount_percent: Decimal
    vat_amount: Decimal
    estimated_total_inc_vat: Decimal
    deposit_total: Decimal
    hold_expires_at: datetime | None
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    customer_profile_id: UUID
    customer_name: str
    customer_email_verified: bool
    created_at: datetime

    @property
    def hire_days(self) -> int:
        """Return the number of chargeable days in the hire."""
        return (self.end_date - self.start_date).days

    def hold_is_overdue(self, now: datetime) -> bool:
        """Return True when the booking is still held and its hold has run out (BR-13)."""
        return (
            self.status is ReservationStatus.HELD
            and self.hold_expires_at is not None
            and now > self.hold_expires_at
        )


@dataclass(frozen=True, slots=True)
class ReservationSearch:
    """Which reservations to list, and which page of them.

    Attributes:
        status: Only reservations in this status, or None for every status.
        customer_profile_id: Only the reservations of this customer, or None.
        branch_id: Only reservations collected at this branch, or None.
        page: The page wanted, counted from one.
        page_size: How many reservations a page holds.

    """

    status: ReservationStatus | None = None
    customer_profile_id: UUID | None = None
    branch_id: UUID | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary validates the same limits and answers with a 422.
        This is the second line, so a caller inside the system cannot hand the
        repository a negative offset or an unbounded page.

        Raises:
            ValueError: If the page or the page size is out of range.

        """
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to list reservations for page {self.page}. A page is between "
                f"{FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to list reservations with a page size of {self.page_size}. A "
                f"page holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} reservations."
            )

    @property
    def offset(self) -> int:
        """Return how many reservations come before the page wanted."""
        return (self.page - FIRST_PAGE) * self.page_size


@dataclass(frozen=True, slots=True)
class ReservationPage:
    """One page of a list of reservations, newest first.

    Attributes:
        items: The reservations on the page.
        page: The page this is, counted from one.
        page_size: How many reservations a page holds.
        total: How many reservations match across every page.

    """

    items: tuple[ReservationDetail, ...]
    page: int
    page_size: int
    total: int
