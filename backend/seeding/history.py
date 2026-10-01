"""Write the worked example as a hire that is already closed.

The reservation, its line, the allocation, the rental, the rental item and the
four charges are one unit of history. I match the unit on the reservation
reference and the rental reference together. Both present means the history is
there and nothing is written. Neither present means all of it is written. One
without the other cannot come from this loader, which writes them in a single
transaction, so that case is refused instead of being patched up.

No audit events are written for it. The audit log records what the application
did, and the application did none of this.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.domain.enums import ChargeStatus, ReleaseReason, RentalStatus, ReservationStatus
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Charge,
    CustomerProfile,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
    UserAccount,
)
from seeding import worked_example as example
from seeding.errors import SeedDataError
from seeding.people import CBD_COUNTER_EMAIL, TRADE_CUSTOMER_EMAIL
from seeding.report import SeedTally
from seeding.worked_example import WorkedExampleFigures

logger = logging.getLogger("seed")

RESERVATION_KIND = "reservation"
RESERVATION_LINE_KIND = "reservation_line"
ALLOCATION_KIND = "asset_allocation"
RENTAL_KIND = "rental"
RENTAL_ITEM_KIND = "rental_item"
CHARGE_KIND = "charge"
SINGLE_ROW_KINDS = (
    RESERVATION_KIND,
    RESERVATION_LINE_KIND,
    ALLOCATION_KIND,
    RENTAL_KIND,
    RENTAL_ITEM_KIND,
)
PAYMENT_REFERENCE_PREFIX = "SIM"


@dataclass(frozen=True, slots=True)
class HistoryParties:
    """The rows the worked example hangs from, already loaded by the earlier steps."""

    branch: Branch
    product_model: ProductModel
    asset: Asset
    customer_account: UserAccount
    customer_profile: CustomerProfile
    counter_assistant: UserAccount


def load_worked_example(
    session: Session,
    branches: dict[str, Branch],
    models: dict[str, ProductModel],
    accounts: dict[str, UserAccount],
    profiles: dict[str, CustomerProfile],
    tally: SeedTally,
) -> None:
    """Insert the closed hire of the worked example unless it is already there.

    Raises:
        SeedDataError: If the reservation exists without the rental or the
            other way round, if the unit on hire is not the documented model at
            the documented branch, or if the model's rates no longer give the
            documented figures.

    """
    reservation_exists = _exists(session, Reservation, example.RESERVATION_REFERENCE)
    rental_exists = _exists(session, Rental, example.RENTAL_REFERENCE)
    if reservation_exists != rental_exists:
        raise SeedDataError(
            f"Found reservation {example.RESERVATION_REFERENCE} "
            f"{'present' if reservation_exists else 'absent'} and rental "
            f"{example.RENTAL_REFERENCE} {'present' if rental_exists else 'absent'}. The seed "
            "writes the two together, so this database was changed by something else. "
            "Remove the half that is there or restore the half that is missing, then run "
            "the seed again."
        )
    if reservation_exists:
        logger.debug(
            "seed.worked_example_found", extra={"reference": example.RESERVATION_REFERENCE}
        )
        _record(tally, created=False)
        return
    parties = _resolve_parties(session, branches, models, accounts, profiles)
    figures = example.compute_figures(
        model_name=parties.product_model.name,
        daily_rate=parties.product_model.daily_rate,
        deposit_amount=parties.product_model.deposit_amount,
        late_fee_per_day=parties.product_model.late_fee_per_day,
    )
    _write_history(session, parties, figures)
    logger.info(
        "seed.worked_example_created",
        extra={
            "reservation_reference": example.RESERVATION_REFERENCE,
            "rental_reference": example.RENTAL_REFERENCE,
            "asset_tag": example.ASSET_TAG,
            "deposit_withheld": str(figures.deposit_withheld),
            "deposit_refunded": str(figures.deposit_refunded),
            "balance_due": str(figures.balance_due),
        },
    )
    _record(tally, created=True)


def _exists(session: Session, table: type[Reservation] | type[Rental], reference: str) -> bool:
    """Return True when a reservation or a rental with this reference is stored."""
    statement = select(col(table.id)).where(col(table.reference) == reference)
    return session.exec(statement).first() is not None


def _record(tally: SeedTally, *, created: bool) -> None:
    """Record the rows of the worked example as all created or all found."""
    counts = {kind: 1 for kind in SINGLE_ROW_KINDS}
    counts[CHARGE_KIND] = example.CHARGE_COUNT
    for kind, count in counts.items():
        tally.record(kind, created=count if created else 0, found=0 if created else count)


def _resolve_parties(
    session: Session,
    branches: dict[str, Branch],
    models: dict[str, ProductModel],
    accounts: dict[str, UserAccount],
    profiles: dict[str, CustomerProfile],
) -> HistoryParties:
    """Return the rows the worked example refers to, checking the unit is the right one."""
    branch = branches[example.BRANCH_CODE]
    product_model = models[example.MODEL_SKU]
    asset = session.exec(
        select(Asset).where(col(Asset.asset_tag) == example.ASSET_TAG)
    ).first()
    if asset is None:
        raise SeedDataError(
            f"The worked example needs asset {example.ASSET_TAG}, which is not in the "
            "database. It is a pinned unit, so load the fleet before the history."
        )
    if asset.product_model_id != product_model.id or asset.branch_id != branch.id:
        raise SeedDataError(
            f"Asset {example.ASSET_TAG} is not a {example.MODEL_SKU} at {example.BRANCH_CODE} "
            "in this database, so the worked example cannot be written against it. The "
            "unit was most likely loaded by an earlier version of the seed."
        )
    return HistoryParties(
        branch=branch,
        product_model=product_model,
        asset=asset,
        customer_account=accounts[TRADE_CUSTOMER_EMAIL],
        customer_profile=profiles[TRADE_CUSTOMER_EMAIL],
        counter_assistant=accounts[CBD_COUNTER_EMAIL],
    )


def _write_history(
    session: Session, parties: HistoryParties, figures: WorkedExampleFigures
) -> None:
    """Insert the nine rows, each parent flushed before the rows that point at it."""
    model = parties.product_model
    reservation = Reservation(
        reference=example.RESERVATION_REFERENCE,
        customer_profile_id=parties.customer_profile.id,
        branch_id=parties.branch.id,
        start_date=example.HIRE_START,
        end_date=example.HIRE_END,
        status=ReservationStatus.RETURNED,
        subtotal_ex_vat=figures.subtotal_ex_vat,
        vat_amount=figures.vat_amount,
        deposit_total=figures.deposit_held,
        estimated_total_inc_vat=figures.total_inc_vat,
        created_by_user_id=parties.customer_account.id,
        confirmed_at=example.BOOKED_AT,
        created_at=example.BOOKED_AT,
    )
    session.add(reservation)
    session.flush()

    line = ReservationLine(
        reservation_id=reservation.id,
        product_model_id=model.id,
        quantity=example.QUANTITY,
        line_position=example.FIRST_LINE_POSITION,
        daily_rate_snapshot=model.daily_rate,
        weekly_rate_snapshot=model.weekly_rate,
        deposit_snapshot=model.deposit_amount,
        late_fee_per_day_snapshot=model.late_fee_per_day,
        replacement_value_snapshot=model.replacement_value,
        line_subtotal_ex_vat=figures.subtotal_ex_vat,
    )
    session.add(line)
    session.flush()

    # Released with its reason, so the allocation is history and does not hold
    # the unit against a new booking of the same dates.
    allocation = AssetAllocation(
        reservation_line_id=line.id,
        asset_id=parties.asset.id,
        branch_id=parties.branch.id,
        start_date=example.HIRE_START,
        end_date=example.HIRE_END,
        allocated_at=example.BOOKED_AT,
        released_at=example.RETURNED_AT,
        release_reason=ReleaseReason.RETURNED,
    )
    session.add(allocation)
    session.flush()

    rental = Rental(
        reference=example.RENTAL_REFERENCE,
        reservation_id=reservation.id,
        branch_id=parties.branch.id,
        status=RentalStatus.SETTLED,
        checked_out_at=example.CHECKED_OUT_AT,
        checked_out_by_user_id=parties.counter_assistant.id,
        due_back_on=example.HIRE_END,
        returned_at=example.RETURNED_AT,
        returned_to_user_id=parties.counter_assistant.id,
        deposit_held=figures.deposit_held,
        deposit_refunded=figures.deposit_refunded,
        deposit_withheld=figures.deposit_withheld,
        balance_due=figures.balance_due,
        settled_at=example.RETURNED_AT,
        agreement_signed=True,
    )
    session.add(rental)
    session.flush()

    item = RentalItem(
        rental_id=rental.id,
        asset_allocation_id=allocation.id,
        asset_id=parties.asset.id,
        condition_out=parties.asset.condition_grade,
        condition_in=parties.asset.condition_grade,
        hour_meter_out=example.HOUR_METER_OUT,
        hour_meter_in=example.HOUR_METER_IN,
        checked_out_at=example.CHECKED_OUT_AT,
        returned_at=example.RETURNED_AT,
        days_late=figures.days_late,
    )
    session.add(item)
    session.flush()

    for position, charge in enumerate(figures.charges, start=1):
        session.add(
            Charge(
                rental_id=rental.id,
                rental_item_id=item.id if charge.attributable_to_item else None,
                charge_type=charge.charge_type,
                description=charge.description,
                amount_ex_vat=charge.amount_ex_vat,
                vat_rate=charge.vat_rate,
                vat_amount=charge.vat_amount,
                amount_inc_vat=charge.amount_inc_vat,
                status=ChargeStatus.SETTLED,
                raised_at=charge.raised_at,
                raised_by_user_id=parties.counter_assistant.id,
                settled_at=charge.raised_at,
                payment_reference=(
                    f"{PAYMENT_REFERENCE_PREFIX}-{example.RENTAL_REFERENCE}-{position:02d}"
                ),
            )
        )
    session.flush()
