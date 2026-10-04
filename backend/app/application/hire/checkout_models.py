"""What the read of a checkout hands back, as small frozen dataclasses.

`CheckoutDetail` is what the counter needs to hand the equipment of one
reservation over, with the units the reservation holds right now and how many
it asks for. It is not a table row. Whether the caller may check it out, and
why not, is worked out from it in `app.application.hire.views`.

A reservation that holds fewer units than it asks for is short, because an
administrator released one by hand (US-32). `units_short` says by how many, and
only a reservation on hold or confirmed is ever short, because those are the
ones still waiting for their units.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.booking_line import NOTHING_SHORT
from app.domain.enums import AccountStatus, ConditionGrade, IdDocType, ReservationStatus

# The bookings that wait for their units, so the only ones that can be short.
WAITING_FOR_UNITS: Final[frozenset[ReservationStatus]] = frozenset(
    {ReservationStatus.HELD, ReservationStatus.CONFIRMED}
)


@dataclass(frozen=True, slots=True)
class CheckoutCustomer:
    """The customer a counter assistant checks the equipment out to."""

    id: UUID
    display_name: str
    phone: str
    id_document_type: IdDocType
    id_document_last4: str
    account_status: AccountStatus


@dataclass(frozen=True, slots=True)
class CheckoutUnit:
    """One unit the reservation holds, as the counter hands it over.

    Attributes:
        allocation_id: The allocation the unit is held under.
        asset_tag: The tag painted on the unit.
        model_name: The name of its model.
        model_slug: Its slug.
        condition_grade: The grade recorded the last time it went out or came back.
        hour_meter: Its last meter reading, for a unit with a meter.
        deposit_per_unit: The deposit copied onto its reservation line.

    """

    allocation_id: UUID
    asset_tag: str
    model_name: str
    model_slug: str
    condition_grade: ConditionGrade
    hour_meter: int | None
    deposit_per_unit: Decimal


@dataclass(frozen=True, slots=True)
class CheckoutDetail:
    """A reservation as the counter sees it at the moment of handing it over.

    Attributes:
        reservation_id: The reservation key.
        reference: Its reference.
        status: Where it stands.
        branch_id: The collection branch.
        branch_code: Its short code.
        branch_name: Its display name.
        customer: The customer it belongs to.
        start_date: The first day of the hire.
        end_date: The day the equipment comes back.
        units: The units it holds right now, in line order and then tag order.
        hire_total_inc_vat: The hire as stored on the reservation, with VAT.
        rental_id: The rental opened from it, once it has been collected.
        units_wanted: How many units its lines ask for in all.

    """

    reservation_id: UUID
    reference: str
    status: ReservationStatus
    branch_id: UUID
    branch_code: str
    branch_name: str
    customer: CheckoutCustomer
    start_date: date
    end_date: date
    units: tuple[CheckoutUnit, ...]
    hire_total_inc_vat: Decimal
    rental_id: UUID | None
    units_wanted: int = NOTHING_SHORT

    @property
    def hire_days(self) -> int:
        """Return the number of chargeable days in the hire."""
        return (self.end_date - self.start_date).days

    @property
    def units_short(self) -> int:
        """Return how many units a reservation waiting for its units still needs."""
        if self.status not in WAITING_FOR_UNITS:
            return NOTHING_SHORT
        return max(self.units_wanted - len(self.units), NOTHING_SHORT)
