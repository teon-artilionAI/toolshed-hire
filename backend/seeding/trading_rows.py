"""Turn what the domain left behind into rows, ready for a bulk insert.

Each builder lists the columns of its table the way the application's own
repositories map an aggregate, so the history reads back through every query
exactly as a hire the counter recorded would. The two timestamps the database
would otherwise stamp with the moment of the load are set to when the row was
made and last changed in the season, so a list ordered by creation shows the
history in its place and not on top of today's work.

The domain gives every new row a random key. `StableKeys` swaps each one for a
key worked out from the reference of the hire and the row's place in it, so a
run on an empty database writes the same keys every time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final
from uuid import NAMESPACE_DNS, UUID, uuid5

from app.domain.charge import Charge
from app.domain.damage import DamageReport
from app.domain.enums import AccountStatus
from app.domain.rental import Rental
from seeding.trading_customers import WalkInProfile
from seeding.trading_hire import HireOutcome
from seeding.trading_records import PlannedHire

type Row = dict[str, object]

# The namespace every stable key of the history is made in. It is a name based
# key made from a fixed name, so it is the same on every machine.
HISTORY_KEY_NAME: Final[str] = "trading-history.seed.toolshedhire.co.za"
HISTORY_KEY_NAMESPACE: Final[UUID] = uuid5(NAMESPACE_DNS, HISTORY_KEY_NAME)
NO_COUNT: Final[int] = 0


class StableKeys:
    """Swaps the random keys the domain made for keys that are the same on every run."""

    def __init__(self) -> None:
        """Start with no key swapped."""
        self._swapped: dict[UUID, UUID] = {}

    def assign(self, made: UUID, label: str) -> None:
        """Give the row the domain keyed `made` the stable key of a label unique to it."""
        self._swapped[made] = uuid5(HISTORY_KEY_NAMESPACE, label)

    def of(self, key: UUID) -> UUID:
        """Return the stable key of a row of the history, or the key unchanged for any other row."""
        return self._swapped.get(key, key)

    def of_optional(self, key: UUID | None) -> UUID | None:
        """Return the stable key of an optional reference, or None."""
        return None if key is None else self.of(key)


@dataclass(slots=True)
class HistoryRows:
    """Every row of the history, by table, in the order the tables are written."""

    customer_profiles: list[Row] = field(default_factory=list)
    reservations: list[Row] = field(default_factory=list)
    reservation_lines: list[Row] = field(default_factory=list)
    asset_allocations: list[Row] = field(default_factory=list)
    rentals: list[Row] = field(default_factory=list)
    rental_items: list[Row] = field(default_factory=list)
    damage_reports: list[Row] = field(default_factory=list)
    charges: list[Row] = field(default_factory=list)


def customer_key(profile: WalkInProfile) -> UUID:
    """Return the stable key of one walk in customer, made from their phone number."""
    return uuid5(HISTORY_KEY_NAMESPACE, f"customer/{profile.key}")


def customer_row(profile: WalkInProfile, branch_id: UUID) -> Row:
    """Return the row of one walk in customer, with no login."""
    details = profile.customer.details
    return {
        "id": customer_key(profile),
        "user_account_id": None,
        "customer_type": profile.customer.customer_type,
        "display_name": details.full_name,
        "company_name": profile.customer.company_name,
        "vat_number": profile.customer.vat_number,
        "id_document_type": details.id_document_type,
        "id_document_last4": details.id_document_last4,
        "contact_phone": details.phone,
        "billing_address_line1": details.billing_address_line1,
        "billing_suburb": details.billing_suburb,
        "billing_city": details.billing_city,
        "billing_postal_code": details.billing_postal_code,
        "account_status": AccountStatus.ACTIVE,
        "trade_discount_percent": profile.trade_discount_percent,
        "no_show_count": NO_COUNT,
        "late_cancellation_count": NO_COUNT,
        "registered_branch_id": branch_id,
        "created_at": profile.registered_at,
        "updated_at": profile.registered_at,
    }


def add_hire_rows(rows: HistoryRows, plan: PlannedHire, outcome: HireOutcome) -> None:
    """Add the rows of one closed hire to the rows of the history, with stable keys."""
    keys = _keys_of(plan, outcome)
    _add_booking(rows, plan, outcome, keys)
    _add_rental(rows, outcome.rental, keys)
    if outcome.report is not None:
        rows.damage_reports.append(_report_row(outcome.report, keys))
    rows.charges.extend(_charge_row(charge, keys) for charge in outcome.rental.charges)


def _keys_of(plan: PlannedHire, outcome: HireOutcome) -> StableKeys:
    """Give every row of one hire a key made from its reference and its place in the hire."""
    keys = StableKeys()
    reservation, rental = outcome.reservation, outcome.rental
    keys.assign(reservation.id, plan.reservation_reference)
    for line in reservation.lines:
        line_label = f"{plan.reservation_reference}/line/{line.line_position}"
        keys.assign(line.id, line_label)
        for number, allocation in enumerate(line.allocations, start=1):
            keys.assign(allocation.id, f"{line_label}/allocation/{number}")
    keys.assign(rental.id, plan.rental_reference)
    for number, item in enumerate(rental.items, start=1):
        keys.assign(item.id, f"{plan.rental_reference}/item/{number}")
    for number, charge in enumerate(rental.charges, start=1):
        keys.assign(charge.id, f"{plan.rental_reference}/charge/{number}")
    if outcome.report is not None:
        keys.assign(outcome.report.id, outcome.report.reference)
    return keys


def _add_booking(
    rows: HistoryRows, plan: PlannedHire, outcome: HireOutcome, keys: StableKeys
) -> None:
    """Add the reservation, its lines and its allocations."""
    reservation = outcome.reservation
    booked_at = plan.times.booked_at
    rows.reservations.append(
        {
            "id": keys.of(reservation.id),
            "reference": reservation.reference,
            "customer_profile_id": reservation.customer_profile_id,
            "branch_id": reservation.branch_id,
            "status": reservation.status,
            "start_date": reservation.period.start,
            "end_date": reservation.period.end,
            "subtotal_ex_vat": reservation.subtotal_ex_vat().amount,
            "vat_amount": reservation.vat_amount,
            "deposit_total": reservation.deposit_total,
            "estimated_total_inc_vat": reservation.estimated_total_inc_vat,
            "hold_expires_at": reservation.hold_expires_at,
            "created_by_user_id": reservation.created_by_user_id,
            "confirmed_at": reservation.confirmed_at,
            "cancelled_at": reservation.cancelled_at,
            "cancellation_reason": reservation.cancellation_reason,
            "notes": reservation.notes,
            "created_at": booked_at,
            "updated_at": plan.returned_at,
        }
    )
    for line in reservation.lines:
        rows.reservation_lines.append(
            {
                "id": keys.of(line.id),
                "reservation_id": keys.of(line.reservation_id),
                "product_model_id": line.product_model_id,
                "quantity": line.quantity,
                "line_position": line.line_position,
                "daily_rate_snapshot": line.daily_rate_snapshot,
                "weekly_rate_snapshot": line.weekly_rate_snapshot,
                "deposit_snapshot": line.deposit_snapshot,
                "late_fee_per_day_snapshot": line.late_fee_per_day_snapshot,
                "replacement_value_snapshot": line.replacement_value_snapshot,
                "discount_percent": line.discount_percent,
                "line_subtotal_ex_vat": line.line_subtotal_ex_vat,
                "created_at": booked_at,
                "updated_at": booked_at,
            }
        )
        rows.asset_allocations.extend(
            {
                "id": keys.of(allocation.id),
                "reservation_line_id": keys.of(allocation.reservation_line_id),
                "asset_id": allocation.asset_id,
                "branch_id": allocation.branch_id,
                "start_date": allocation.period.start,
                "end_date": allocation.period.end,
                "allocated_at": allocation.allocated_at,
                "released_at": allocation.released_at,
                "release_reason": allocation.release_reason,
                "created_at": allocation.allocated_at,
                "updated_at": allocation.released_at,
            }
            for allocation in line.allocations
        )


def _add_rental(rows: HistoryRows, rental: Rental, keys: StableKeys) -> None:
    """Add the rental and its items."""
    rows.rentals.append(
        {
            "id": keys.of(rental.id),
            "reference": rental.reference,
            "reservation_id": keys.of(rental.reservation_id),
            "branch_id": rental.branch_id,
            "status": rental.status,
            "checked_out_at": rental.checked_out_at,
            "checked_out_by_user_id": rental.checked_out_by_user_id,
            "due_back_on": rental.due_back_on,
            "returned_at": rental.returned_at,
            "returned_to_user_id": rental.returned_to_user_id,
            "deposit_held": rental.deposit_held,
            "deposit_refunded": rental.deposit_refunded,
            "deposit_withheld": rental.deposit_withheld,
            "balance_due": rental.balance_due,
            "settled_at": rental.settled_at,
            "agreement_signed": rental.agreement_signed,
            "created_at": rental.checked_out_at,
            "updated_at": rental.settled_at,
        }
    )
    rows.rental_items.extend(
        {
            "id": keys.of(item.id),
            "rental_id": keys.of(item.rental_id),
            "asset_allocation_id": keys.of(item.asset_allocation_id),
            "asset_id": item.asset_id,
            "condition_out": item.condition_out,
            "condition_in": item.condition_in,
            "hour_meter_out": item.hour_meter_out,
            "hour_meter_in": item.hour_meter_in,
            "accessories_out": item.accessories_out,
            "accessories_in": item.accessories_in,
            "checked_out_at": item.checked_out_at,
            "returned_at": item.returned_at,
            "days_late": item.days_late,
            "notes": item.notes,
            "flagged_for_damage": item.flagged_for_damage,
            "created_at": item.checked_out_at,
            "updated_at": item.returned_at,
        }
        for item in rental.items
    )


def _report_row(report: DamageReport, keys: StableKeys) -> Row:
    """Return the row of one resolved damage report."""
    return {
        "id": keys.of(report.id),
        "reference": report.reference,
        "asset_id": report.asset_id,
        "rental_item_id": keys.of_optional(report.rental_item_id),
        "severity": report.severity,
        "status": report.status,
        "description": report.description,
        "photo_path": None,
        "repair_estimate": report.repair_estimate,
        "actual_repair_cost": report.actual_repair_cost,
        "chargeable_to_customer": report.chargeable_to_customer,
        "reported_by_user_id": report.reported_by_user_id,
        "reported_at": report.reported_at,
        "resolved_at": report.resolved_at,
        "resolution_notes": report.resolution_notes,
        "created_at": report.reported_at,
        "updated_at": report.resolved_at,
    }


def _charge_row(charge: Charge, keys: StableKeys) -> Row:
    """Return the row of one charge, as the rental repository writes it."""
    return {
        "id": keys.of(charge.id),
        "rental_id": keys.of(charge.rental_id),
        "rental_item_id": keys.of_optional(charge.rental_item_id),
        "damage_report_id": keys.of_optional(charge.damage_report_id),
        "charge_type": charge.charge_type,
        "description": charge.description,
        "amount_ex_vat": charge.amount_ex_vat,
        "vat_rate": charge.vat_rate,
        "vat_amount": charge.vat_amount,
        "amount_inc_vat": charge.amount_inc_vat,
        "status": charge.status,
        "raised_at": charge.raised_at,
        "raised_by_user_id": charge.raised_by_user_id,
        "settled_at": charge.settled_at,
        "payment_reference": charge.payment_reference,
        # No charge of the history was ever corrected, so none reverses another
        # and none carries the reason an administrator gives for a correction.
        "reverses_charge_id": None,
        "waiver_reason": None,
        "created_at": charge.raised_at,
        "updated_at": charge.settled_at or charge.raised_at,
    }


def counts_of(rows: HistoryRows) -> Iterable[tuple[str, int]]:
    """Yield how many rows of each table the history holds, in the order they are written."""
    yield "customer_profile", len(rows.customer_profiles)
    yield "reservation", len(rows.reservations)
    yield "reservation_line", len(rows.reservation_lines)
    yield "asset_allocation", len(rows.asset_allocations)
    yield "rental", len(rows.rentals)
    yield "rental_item", len(rows.rental_items)
    yield "damage_report", len(rows.damage_reports)
    yield "charge", len(rows.charges)
