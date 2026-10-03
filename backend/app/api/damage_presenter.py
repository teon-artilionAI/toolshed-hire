"""What the damage report routes share, which is the path key, the request and the response.

A report is written out the same way by every route that returns one, so the
mapping from the read model to the `DamageReport` shape of the contract is here
once. An amount arrives as text and becomes `Money` here, so the use cases
never see a string where an amount belongs. Nothing else is worked out in it.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Path

from app.api.damage_schemas import (
    DamageReportPageResponse,
    DamageReportRequest,
    DamageReportResponse,
)
from app.application.hire.damage_models import DamageReportDetail, DamageReportPage
from app.domain.damage_filing import DamageFiling
from app.domain.money import Money

DAMAGE_REPORTS_PREFIX: Final[str] = "/damage-reports"
# The name of the route that reads one report. The `Location` header of a new
# report is built from it.
READ_DAMAGE_REPORT_ROUTE_NAME: Final[str] = "read_damage_report"
# A key is a UUID and a reference is shorter, so nothing longer names a report.
REPORT_KEY_MAX_LENGTH: Final[int] = 36

ReportPathKey = Annotated[
    str,
    Path(
        alias="id",
        min_length=1,
        max_length=REPORT_KEY_MAX_LENGTH,
        description="The key of the damage report, or its reference.",
    ),
]


def amount_of(text: str | None) -> Money | None:
    """Return an amount the request carried as text, or None when it carried none."""
    return None if text is None else Money.create(text)


def filing_of(payload: DamageReportRequest) -> DamageFiling:
    """Return what the counter stated about the damage, from the request."""
    estimate = Money.create(payload.repair_estimate)
    return DamageFiling(
        rental_item_id=payload.rental_item_id,
        severity=payload.severity,
        description=payload.description,
        repair_estimate=estimate,
        chargeable_to_customer=payload.chargeable_to_customer,
        recovery_amount=amount_of(payload.recovery_amount),
    )


def report_response(detail: DamageReportDetail) -> DamageReportResponse:
    """Write a report in the shape the contract gives it."""
    return DamageReportResponse(
        id=detail.id,
        reference=detail.reference,
        asset_tag=detail.asset_tag,
        model_name=detail.model_name,
        branch_code=detail.branch_code,
        rental_id=detail.rental_id,
        rental_reference=detail.rental_reference,
        rental_item_id=detail.rental_item_id,
        severity=detail.severity,
        status=detail.status,
        description=detail.description,
        repair_estimate=detail.repair_estimate,
        actual_repair_cost=detail.actual_repair_cost,
        chargeable_to_customer=detail.chargeable_to_customer,
        recovery_charged=detail.recovery_charged,
        replacement_value=detail.replacement_value,
        reported_at=detail.reported_at,
        reported_by_name=detail.reported_by_name,
        resolved_at=detail.resolved_at,
        resolution_notes=detail.resolution_notes,
    )


def report_page_response(page: DamageReportPage) -> DamageReportPageResponse:
    """Write one page of reports in the shape the contract gives a list."""
    return DamageReportPageResponse(
        items=[report_response(detail) for detail in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )
