"""The seeded worked example is the hire the design document describes.

Reservation TSH-R-26-000123 put TSH-DR-0042 out from the CBD branch for four
days. The unit came back two days late, the late fee was taken out of the
deposit and the rest was released. The seed writes that as history which is
already closed, and the figures below are read back from the database, where
the check constraints on the rental and the charge have already had their say.
A deposit movement carrying VAT or a closed rental with no return time would
have been refused before any of these assertions ran.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import (
    AssetStatus,
    ChargeStatus,
    ChargeType,
    ReleaseReason,
    RentalStatus,
    ReservationStatus,
)
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Charge,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
)

pytestmark = pytest.mark.postgres

WORKED_EXAMPLE_TAG: Final[str] = "TSH-DR-0042"
WORKED_EXAMPLE_SKU: Final[str] = "DR-BOSCH-GBH226"
RESERVATION_REFERENCE: Final[str] = "TSH-R-26-000123"
RENTAL_REFERENCE: Final[str] = "TSH-H-26-000098"
HIRE_DAYS: Final[int] = 4
DAYS_LATE: Final[int] = 2

# charge type, before VAT, VAT rate, VAT, including VAT
EXPECTED_CHARGES: Final[dict[ChargeType, tuple[str, str, str, str]]] = {
    ChargeType.HIRE: ("1120.00", "15.00", "168.00", "1288.00"),
    ChargeType.DEPOSIT_HOLD: ("1200.00", "0.00", "0.00", "1200.00"),
    ChargeType.LATE_FEE: ("208.70", "15.00", "31.30", "240.00"),
    ChargeType.DEPOSIT_RELEASE: ("-960.00", "0.00", "0.00", "-960.00"),
}


def worked_example_rental(reader: Session) -> Rental:
    """Return the rental of the worked example, which the seed must have written."""
    return reader.exec(select(Rental).where(col(Rental.reference) == RENTAL_REFERENCE)).one()


def charges_of(reader: Session, rental: Rental) -> list[Charge]:
    """Return every charge raised on a rental."""
    return list(reader.exec(select(Charge).where(col(Charge.rental_id) == rental.id)).all())


class TestTheWorkedExampleUnit:
    """TSH-DR-0042 is the unit the design document follows through a hire."""

    def test_it_is_a_bosch_gbh_2_26_at_the_cbd_branch(self, reader: Session) -> None:
        asset = reader.exec(
            select(Asset).where(col(Asset.asset_tag) == WORKED_EXAMPLE_TAG)
        ).one()
        model = reader.get(ProductModel, asset.product_model_id)
        branch = reader.get(Branch, asset.branch_id)
        assert model is not None and branch is not None
        assert model.sku == WORKED_EXAMPLE_SKU
        assert model.manufacturer == "Bosch"
        assert "GBH 2-26" in model.name
        assert branch.code == "CBD"

    def test_it_is_available_again_after_the_closed_hire(self, reader: Session) -> None:
        asset = reader.exec(
            select(Asset).where(col(Asset.asset_tag) == WORKED_EXAMPLE_TAG)
        ).one()
        active = reader.exec(
            select(AssetAllocation).where(
                col(AssetAllocation.asset_id) == asset.id,
                col(AssetAllocation.released_at).is_(None),
            )
        ).all()
        assert asset.status is AssetStatus.AVAILABLE
        assert not active


class TestTheWorkedExampleHire:
    """The figures the design document states, read back from the database."""

    def test_the_reservation_is_returned_and_covers_four_hire_days(self, reader: Session) -> None:
        reservation = reader.exec(
            select(Reservation).where(col(Reservation.reference) == RESERVATION_REFERENCE)
        ).one()
        assert reservation.status is ReservationStatus.RETURNED
        assert reservation.hire_days == HIRE_DAYS

    def test_the_allocation_was_released_because_the_unit_was_returned(
        self, reader: Session
    ) -> None:
        allocation = reader.exec(select(AssetAllocation)).one()
        assert allocation.released_at is not None
        assert allocation.release_reason is ReleaseReason.RETURNED

    def test_the_rental_is_settled_with_the_late_fee_taken_from_the_deposit(
        self, reader: Session
    ) -> None:
        rental = worked_example_rental(reader)
        assert rental.status is RentalStatus.SETTLED
        assert rental.deposit_held == Decimal("1200.00")
        assert rental.deposit_withheld == Decimal("240.00")
        assert rental.deposit_refunded == Decimal("960.00")
        assert rental.balance_due == Decimal("0.00")

    def test_the_one_item_came_back_two_days_late_in_the_condition_it_left_in(
        self, reader: Session
    ) -> None:
        item = reader.exec(select(RentalItem)).one()
        asset = reader.get(Asset, item.asset_id)
        assert asset is not None
        assert asset.asset_tag == WORKED_EXAMPLE_TAG
        assert item.days_late == DAYS_LATE
        assert item.condition_out is asset.condition_grade
        assert item.condition_in is asset.condition_grade

    def test_the_four_charges_carry_the_documented_amounts(self, reader: Session) -> None:
        rental = worked_example_rental(reader)
        charges = charges_of(reader, rental)
        found = {
            charge.charge_type: (
                str(charge.amount_ex_vat),
                str(charge.vat_rate),
                str(charge.vat_amount),
                str(charge.amount_inc_vat),
            )
            for charge in charges
        }
        assert len(charges) == len(EXPECTED_CHARGES)
        assert found == EXPECTED_CHARGES
        assert all(charge.status is ChargeStatus.SETTLED for charge in charges)

    def test_the_charges_add_up_to_the_settlement_on_the_rental(self, reader: Session) -> None:
        """What was kept of the deposit is what was taken less what was released.

        The amount kept pays the late fee, which is why nothing is left due.
        """
        rental = worked_example_rental(reader)
        charges = charges_of(reader, rental)
        by_type = {charge.charge_type: charge for charge in charges}
        deposit_kept = (
            by_type[ChargeType.DEPOSIT_HOLD].amount_inc_vat
            + by_type[ChargeType.DEPOSIT_RELEASE].amount_inc_vat
        )
        assert all(
            charge.amount_inc_vat == charge.amount_ex_vat + charge.vat_amount
            for charge in charges
        )
        assert deposit_kept == rental.deposit_withheld
        assert by_type[ChargeType.LATE_FEE].amount_inc_vat - deposit_kept == rental.balance_due
        assert sum(charge.amount_ex_vat for charge in charges) == Decimal("1568.70")
        assert sum(charge.vat_amount for charge in charges) == Decimal("199.30")
        assert sum(charge.amount_inc_vat for charge in charges) == Decimal("1768.00")
