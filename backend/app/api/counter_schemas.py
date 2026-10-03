"""Response models for the counter's dashboard, diary and asset locator.

Field names on the wire are camelCase, as everywhere else at this boundary.
Money is a string with two decimals and a date is `YYYY-MM-DD`.

`summary` says what a booking holds in a few words, for example
`2 x Bosch GBH 2-26`, so the screen can show it on one line. `canMarkNoShow`
says whether the caller may mark a collection as not collected right now. It is
worked out on the server from the rule the route enforces, so the button and
the route agree.

All three are for staff, so the locator carries the tag of every unit.
"""

from __future__ import annotations

from datetime import date
from typing import Final
from uuid import UUID

from pydantic import ConfigDict, Field

from app.api.catalogue_schemas import Money
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.enums import AssetStatus, ConditionGrade, RentalStatus, ReservationStatus

WRONG_BRANCH_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The caller is not staff, or counter staff named another branch.",
}


class DashboardCountsResponse(CamelModel):
    """The true totals behind the dashboard, however long each list is."""

    collections_due: int = Field(serialization_alias="collectionsDue")
    returns_due: int = Field(serialization_alias="returnsDue")
    overdue: int
    on_hire: int = Field(serialization_alias="onHire")
    quarantined: int


class CollectionDueResponse(CamelModel):
    """A confirmed reservation due for collection."""

    reservation_id: UUID = Field(serialization_alias="reservationId")
    reference: str
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    unit_count: int = Field(serialization_alias="unitCount")
    summary: str


class ReturnDueResponse(CamelModel):
    """A rental due back today with a unit still out."""

    rental_id: UUID = Field(serialization_alias="rentalId")
    reference: str
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    due_back_on: date = Field(serialization_alias="dueBackOn")
    items_out: int = Field(serialization_alias="itemsOut")
    item_count: int = Field(serialization_alias="itemCount")
    summary: str


class OverdueRentalResponse(CamelModel):
    """A rental past its due date with a unit still out, and the late fee it has run up."""

    rental_id: UUID = Field(serialization_alias="rentalId")
    reference: str
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    due_back_on: date = Field(serialization_alias="dueBackOn")
    days_overdue: int = Field(serialization_alias="daysOverdue")
    items_out: int = Field(serialization_alias="itemsOut")
    late_fee_accrued: Money = Field(serialization_alias="lateFeeAccrued")


class DashboardResponse(CamelModel):
    """What is due today at one branch. Each list holds at most fifty rows."""

    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    business_day: date = Field(serialization_alias="date")
    counts: DashboardCountsResponse
    collections_due: list[CollectionDueResponse] = Field(serialization_alias="collectionsDue")
    returns_due: list[ReturnDueResponse] = Field(serialization_alias="returnsDue")
    overdue: list[OverdueRentalResponse]


class DiaryCollectionResponse(CamelModel):
    """A reservation starting on a day of the diary."""

    reservation_id: UUID = Field(serialization_alias="reservationId")
    reference: str
    status: ReservationStatus
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    unit_count: int = Field(serialization_alias="unitCount")
    summary: str
    can_mark_no_show: bool = Field(serialization_alias="canMarkNoShow")


class DiaryReturnResponse(CamelModel):
    """A rental due back on a day of the diary."""

    rental_id: UUID = Field(serialization_alias="rentalId")
    reference: str
    status: RentalStatus
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    due_back_on: date = Field(serialization_alias="dueBackOn")
    items_out: int = Field(serialization_alias="itemsOut")
    item_count: int = Field(serialization_alias="itemCount")
    summary: str


class DiaryDayResponse(CamelModel):
    """One day of the diary."""

    business_day: date = Field(serialization_alias="date")
    collections: list[DiaryCollectionResponse]
    returns: list[DiaryReturnResponse]


class DiaryResponse(CamelModel):
    """The diary of one branch, one entry for each day asked for."""

    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    days: list[DiaryDayResponse]


class AssetLocationResponse(CamelModel):
    """Where one unit is. `dueBackOn` and `rentalReference` are set only while it is on hire."""

    asset_tag: str = Field(serialization_alias="assetTag")
    model_name: str = Field(serialization_alias="modelName")
    model_slug: str = Field(serialization_alias="modelSlug")
    category_name: str = Field(serialization_alias="categoryName")
    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    status: AssetStatus
    condition_grade: ConditionGrade = Field(serialization_alias="conditionGrade")
    due_back_on: date | None = Field(serialization_alias="dueBackOn")
    rental_reference: str | None = Field(serialization_alias="rentalReference")

    # `model_name` and `model_slug` are the documented names and collide with nothing.
    model_config = ConfigDict(protected_namespaces=())


class AssetLocationPageResponse(CamelModel):
    """One page of the units a search found, in tag order."""

    items: list[AssetLocationResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int
