"""How the counter's dashboard, diary and asset locator are written in the shape of the contract.

Nothing is worked out here. Every figure and every flag was decided before it
reached this module, and this only maps the read models to the responses.
"""

from __future__ import annotations

from app.api.counter_schemas import (
    AssetLocationPageResponse,
    AssetLocationResponse,
    CollectionDueResponse,
    DashboardCountsResponse,
    DashboardResponse,
    DiaryCollectionResponse,
    DiaryDayResponse,
    DiaryResponse,
    DiaryReturnResponse,
    OverdueRentalResponse,
    ReturnDueResponse,
)
from app.application.catalogue.locator import AssetLocation, AssetLocationPage
from app.application.hire.overview_models import (
    BranchDashboard,
    BranchDiary,
    CollectionEntry,
    DiaryCollection,
    OverdueEntry,
    ReturnEntry,
)


def dashboard_response(dashboard: BranchDashboard) -> DashboardResponse:
    """Write the dashboard of a branch."""
    counts = dashboard.counts
    return DashboardResponse(
        branch_code=dashboard.branch.code,
        branch_name=dashboard.branch.name,
        business_day=dashboard.business_day,
        counts=DashboardCountsResponse(
            collections_due=counts.collections_due,
            returns_due=counts.returns_due,
            overdue=counts.overdue,
            on_hire=counts.on_hire,
            quarantined=counts.quarantined,
        ),
        collections_due=[_collection_due(entry) for entry in dashboard.collections_due],
        returns_due=[_return_due(entry) for entry in dashboard.returns_due],
        overdue=[_overdue(entry) for entry in dashboard.overdue],
    )


def diary_response(diary: BranchDiary) -> DiaryResponse:
    """Write the diary of a branch, one entry for each day."""
    return DiaryResponse(
        branch_code=diary.branch.code,
        branch_name=diary.branch.name,
        days=[
            DiaryDayResponse(
                business_day=day.business_day,
                collections=[_diary_collection(collection) for collection in day.collections],
                returns=[_diary_return(entry) for entry in day.returns],
            )
            for day in diary.days
        ],
    )


def locator_response(found: AssetLocationPage) -> AssetLocationPageResponse:
    """Write one page of the units the locator found."""
    return AssetLocationPageResponse(
        items=[_location(location) for location in found.items],
        page=found.page,
        page_size=found.page_size,
        total=found.total,
    )


def _collection_due(entry: CollectionEntry) -> CollectionDueResponse:
    """Write one collection of the dashboard."""
    return CollectionDueResponse(
        reservation_id=entry.reservation_id,
        reference=entry.reference,
        customer_name=entry.customer_name,
        customer_phone=entry.customer_phone,
        from_date=entry.start_date,
        to_date=entry.end_date,
        unit_count=entry.unit_count,
        summary=entry.summary,
    )


def _return_due(entry: ReturnEntry) -> ReturnDueResponse:
    """Write one return of the dashboard."""
    return ReturnDueResponse(
        rental_id=entry.rental_id,
        reference=entry.reference,
        customer_name=entry.customer_name,
        customer_phone=entry.customer_phone,
        due_back_on=entry.due_back_on,
        items_out=entry.items_out,
        item_count=entry.item_count,
        summary=entry.summary,
    )


def _overdue(entry: OverdueEntry) -> OverdueRentalResponse:
    """Write one overdue hire of the dashboard."""
    rental = entry.rental
    return OverdueRentalResponse(
        rental_id=rental.rental_id,
        reference=rental.reference,
        customer_name=rental.customer_name,
        customer_phone=rental.customer_phone,
        due_back_on=rental.due_back_on,
        days_overdue=entry.days_overdue,
        items_out=rental.items_out,
        late_fee_accrued=entry.late_fee_accrued,
    )


def _diary_collection(collection: DiaryCollection) -> DiaryCollectionResponse:
    """Write one collection of the diary."""
    entry = collection.entry
    return DiaryCollectionResponse(
        reservation_id=entry.reservation_id,
        reference=entry.reference,
        status=entry.status,
        customer_name=entry.customer_name,
        customer_phone=entry.customer_phone,
        from_date=entry.start_date,
        to_date=entry.end_date,
        unit_count=entry.unit_count,
        summary=entry.summary,
        can_mark_no_show=collection.can_mark_no_show,
    )


def _diary_return(entry: ReturnEntry) -> DiaryReturnResponse:
    """Write one return of the diary."""
    return DiaryReturnResponse(
        rental_id=entry.rental_id,
        reference=entry.reference,
        status=entry.status,
        customer_name=entry.customer_name,
        customer_phone=entry.customer_phone,
        due_back_on=entry.due_back_on,
        items_out=entry.items_out,
        item_count=entry.item_count,
        summary=entry.summary,
    )


def _location(location: AssetLocation) -> AssetLocationResponse:
    """Write where one unit is."""
    return AssetLocationResponse(
        asset_tag=location.asset_tag,
        model_name=location.model_name,
        model_slug=location.model_slug,
        category_name=location.category_name,
        branch_code=location.branch_code,
        branch_name=location.branch_name,
        status=location.status,
        condition_grade=location.condition_grade,
        due_back_on=location.due_back_on,
        rental_reference=location.rental_reference,
    )
