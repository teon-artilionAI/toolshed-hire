"""What the checkout and rental routes share, which is the path keys and the responses.

A rental is written out the same way by every route that returns one, so the
mapping from what a use case hands back to the `Rental` shape of the contract
is here once, and so is the mapping to the checkout shape. Nothing is worked
out in it. Every figure and every flag was decided before it reached this
module.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Path

from app.api.hire_schemas import (
    ChargeResponse,
    CheckoutCustomerResponse,
    CheckoutPreviewResponse,
    CheckoutUnitResponse,
    RentalItemResponse,
    RentalResponse,
)
from app.api.return_schemas import RentalPageResponse
from app.application.hire.views import CheckoutView, RentalView, RentalViewPage

RENTALS_PREFIX: Final[str] = "/rentals"
# The tag of both routers, which is the module they belong to.
HIRE_TAG: Final[str] = "hire"
# The name of the route that reads one rental. The `Location` header of a new
# rental is built from it.
READ_RENTAL_ROUTE_NAME: Final[str] = "read_rental"
# A key is a UUID and a reference is shorter, so nothing longer names a rental.
RENTAL_KEY_MAX_LENGTH: Final[int] = 36

RentalPathKey = Annotated[
    str,
    Path(
        alias="id",
        min_length=1,
        max_length=RENTAL_KEY_MAX_LENGTH,
        description="The key of the rental, or its reference.",
    ),
]


def rental_response(view: RentalView) -> RentalResponse:
    """Write a rental in the shape the contract gives it."""
    detail = view.detail
    return RentalResponse(
        id=detail.id,
        reference=detail.reference,
        status=detail.status,
        reservation_id=detail.reservation_id,
        reservation_reference=detail.reservation_reference,
        branch_code=detail.branch_code,
        branch_name=detail.branch_name,
        customer_profile_id=detail.customer_profile_id,
        customer_name=detail.customer_name,
        customer_phone=detail.customer_phone,
        from_date=detail.start_date,
        due_back_on=detail.due_back_on,
        checked_out_at=detail.checked_out_at,
        returned_at=detail.returned_at,
        items=[
            RentalItemResponse(
                id=shown.item.id,
                asset_tag=shown.item.asset_tag,
                model_name=shown.item.model_name,
                model_slug=shown.item.model_slug,
                condition_out=shown.item.condition_out,
                condition_in=shown.item.condition_in,
                hour_meter_out=shown.item.hour_meter_out,
                hour_meter_in=shown.item.hour_meter_in,
                accessories_out=shown.item.accessories_out,
                accessories_in=shown.item.accessories_in,
                returned_at=shown.item.returned_at,
                days_late=shown.item.days_late,
                late_fee_per_day=shown.item.late_fee_per_day,
                days_late_today=shown.days_late_today,
                late_fee_today=shown.late_fee_today,
                damage_assessment=shown.damage_assessment,
            )
            for shown in view.items
        ],
        charges=[
            ChargeResponse(
                id=charge.id,
                charge_type=charge.charge_type,
                description=charge.description,
                amount_ex_vat=charge.amount_ex_vat,
                vat_rate=charge.vat_rate,
                vat_amount=charge.vat_amount,
                amount_inc_vat=charge.amount_inc_vat,
                status=charge.status,
                raised_at=charge.raised_at,
                rental_item_id=charge.rental_item_id,
            )
            for charge in detail.charges
        ],
        deposit_held=detail.deposit_held,
        deposit_withheld=detail.deposit_withheld,
        deposit_refunded=detail.deposit_refunded,
        balance_due=detail.balance_due,
        settled_at=detail.settled_at,
        agreement_signed=detail.agreement_signed,
        can_return=view.can_return,
        settlement_waiting_on=view.settlement_waiting_on,
    )


def rental_page_response(page: RentalViewPage) -> RentalPageResponse:
    """Write one page of rentals in the shape the contract gives a list."""
    return RentalPageResponse(
        items=[rental_response(view) for view in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )


def checkout_response(view: CheckoutView) -> CheckoutPreviewResponse:
    """Write a reservation as the counter checks it out, in the shape the contract gives it."""
    detail = view.detail
    customer = detail.customer
    return CheckoutPreviewResponse(
        reservation_id=detail.reservation_id,
        reference=detail.reference,
        status=detail.status,
        branch_code=detail.branch_code,
        branch_name=detail.branch_name,
        customer=CheckoutCustomerResponse(
            id=customer.id,
            display_name=customer.display_name,
            phone=customer.phone,
            id_document_type=customer.id_document_type,
            id_document_last4=customer.id_document_last4,
            account_status=customer.account_status,
        ),
        from_date=detail.start_date,
        to_date=detail.end_date,
        hire_days=detail.hire_days,
        units=[
            CheckoutUnitResponse(
                allocation_id=unit.allocation_id,
                asset_tag=unit.asset_tag,
                model_name=unit.model_name,
                model_slug=unit.model_slug,
                condition_grade=unit.condition_grade,
                hour_meter=unit.hour_meter,
                deposit_per_unit=unit.deposit_per_unit,
            )
            for unit in detail.units
        ],
        hire_total_inc_vat=detail.hire_total_inc_vat,
        deposit_total=view.deposit_total,
        can_check_out=view.can_check_out,
        refusal=view.refusal,
        rental_id=detail.rental_id,
    )
