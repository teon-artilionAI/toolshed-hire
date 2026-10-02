"""The availability query object, which the design document calls SearchAvailabilityQuery.

This is the read side of the availability module. It answers where a model is
free for a period, for a visitor with no account, and it takes no lock.

A unit is free for a period when its status is `AVAILABLE` and it holds no
active allocation whose half open period overlaps the one asked about (BR-10).
A unit in any other status is never free, whatever its bookings say (FR-04).
The rule is written once, in `_free_unit_conditions`.

HOW THE STATEMENT USES THE INDEXES

The list is answered by one statement. A common table expression picks the
models of the page, and the outer query joins that page to every active branch
and tests each pair of model and branch with EXISTS. A page of fifty models
and three branches is a hundred and fifty answers in one round trip, and no
loop in Python issues a statement. Each half of the test lines up with an index.

1. `ix_asset_available` is a partial btree on `(product_model_id, branch_id)
   WHERE status = 'AVAILABLE'`. The test supplies both keys and the status.
   The status is written into the statement as a constant, because the planner
   can only use a partial index when it can prove the predicate from the text
   of the query.
2. The GiST index behind the constraint `asset_allocation_no_overlap` covers
   `asset_id` and `daterange(start_date, end_date, '[)')` for rows `WHERE
   released_at IS NULL`. The NOT EXISTS uses the same range expression, the
   overlap operator and the same predicate, so that index can answer it. A
   released allocation is not in it at all, so past hires cost a search nothing.

The planner runs it one of two ways, and I have watched it choose both. For
one model it probes, `ix_asset_available` for the units and then the GiST index
by unit and range. For a whole page it answers every pair at once. It reads the
active allocations that overlap the period from the GiST index by range alone,
takes them away from the available units and hashes what is left. On the seeded
database, where 400 units fit in seven pages, it does that with plain scans.

AT TEN TIMES THE DATA

I loaded 4,000 units and 250,000 allocation rows, 10,000 of them active, in a
transaction I rolled back, and ran the same statements. A page of fifty took
2 ms and the single model question 0.3 ms. The 240,000 released rows were never
read. The cost follows the available units and the active allocations that
overlap the period, which the fleet and the ninety day horizon bound.

The first thing to slow down is a search narrowed to one branch. The free unit
test then runs three times, in the count, in the page filter and for the
answers. It took 3 ms for the page and 1 ms for the count. The fix, if it ever
shows in the log, is to work the free units of the branch out once and reuse
them. The count is the second, since it reads every matching model on every
request.

Nothing here returns an asset tag, a serial number or a count. The single
model question counts free units inside the database and returns only whether
there are enough (US-07).
"""

from __future__ import annotations

import logging
from itertools import groupby
from typing import Final
from uuid import UUID

from sqlalchemy import (
    ColumnClause,
    ColumnElement,
    Executable,
    RowMapping,
    exists,
    func,
    literal,
    literal_column,
    select,
    true,
)
from sqlalchemy.orm import Mapped, aliased
from sqlmodel import Session, col

from app.application.availability.read_models import (
    AvailabilityPage,
    AvailabilitySearch,
    BranchAvailability,
    ModelAvailability,
)
from app.domain.enums import AssetStatus
from app.domain.period import DATERANGE_BOUNDS, BookingPeriod
from app.infrastructure.catalogue_sql import (
    model_conditions,
    search_filters,
    sort_columns,
    summary_columns,
    summary_of,
)
from app.infrastructure.models import Asset, AssetAllocation, Branch, Category, ProductModel
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

type KeyExpression = ColumnElement[UUID] | Mapped[UUID]

PAGE_CTE_NAME: Final[str] = "page"
# The bound specifier of the exclusion constraint, quoted as SQL. It is part of
# the statement text so the range expression below is the very expression the
# GiST index was built on. A bound parameter in its place would not match.
_HALF_OPEN_BOUNDS: Final[ColumnClause[str]] = literal_column(f"'{DATERANGE_BOUNDS}'")
_RANGE_OVERLAP_OPERATOR: Final[str] = "&&"


def _free_unit_conditions(
    model_id: KeyExpression, branch_id: KeyExpression, period: BookingPeriod
) -> list[ColumnElement[bool]]:
    """Return the conditions that make a unit free for a period (BR-10).

    Args:
        model_id: The product model the unit must realise.
        branch_id: The branch the unit must be at.
        period: The half open hire period.

    """
    held = func.daterange(
        col(AssetAllocation.start_date), col(AssetAllocation.end_date), _HALF_OPEN_BOUNDS
    )
    wanted = func.daterange(period.start, period.end, _HALF_OPEN_BOUNDS)
    blocking_allocation = (
        select(col(AssetAllocation.id))
        .where(
            col(AssetAllocation.asset_id) == col(Asset.id),
            col(AssetAllocation.released_at).is_(None),
            held.op(_RANGE_OVERLAP_OPERATOR)(wanted),
        )
        .correlate(Asset)
    )
    # literal_execute writes the status into the statement as a constant, which
    # is what lets the planner match the partial index. The value is a member
    # of a server side enumeration and never anything a request supplied. It
    # takes the type of the column it is compared with.
    available = literal(AssetStatus.AVAILABLE, literal_execute=True)
    return [
        col(Asset.product_model_id) == model_id,
        col(Asset.branch_id) == branch_id,
        col(Asset.status) == available,
        ~exists(blocking_allocation),
    ]


def availability_page_statement(search: AvailabilitySearch) -> Executable:
    """Return the one statement that answers a page of an availability search.

    The rows come back one per model and branch, the models in the order of
    the search and the branches by name and then code under each model. An
    outer join keeps a model on the page even if no branch is active.
    """
    order = sort_columns(search.models.sort)
    page = (
        select(col(ProductModel.id).label("model_id"))
        .where(*_search_conditions(search))
        .order_by(*order)
        .limit(search.models.page_size)
        .offset(search.models.offset)
        .cte(PAGE_CTE_NAME)
    )
    free_here = exists(
        select(col(Asset.id)).where(
            *_free_unit_conditions(col(ProductModel.id), col(Branch.id), search.period)
        )
    )
    return (
        select(
            *summary_columns(),
            col(Branch.code).label("branch_code"),
            col(Branch.name).label("branch_name"),
            free_here.label("available"),
        )
        .select_from(page)
        .join(ProductModel, col(ProductModel.id) == page.c.model_id)
        .join(Category, col(Category.id) == col(ProductModel.category_id))
        .outerjoin(Branch, col(Branch.is_active) == true())
        .order_by(*order, col(Branch.name), col(Branch.code))
    )


def availability_count_statement(search: AvailabilitySearch) -> Executable:
    """Return the statement that counts the models an availability search matches."""
    return select(func.count()).select_from(ProductModel).where(*_search_conditions(search))


def model_availability_statement(
    model_slug: str, period: BookingPeriod, quantity: int
) -> Executable:
    """Return the statement that answers for one model at every active branch.

    The free units are counted inside the database and compared with the
    quantity there. Only the result of the comparison is selected.
    """
    model_id = (
        select(col(ProductModel.id))
        .where(col(ProductModel.slug) == model_slug, col(ProductModel.is_published) == true())
        .scalar_subquery()
    )
    free_units = (
        select(func.count())
        .select_from(Asset)
        .where(*_free_unit_conditions(model_id, col(Branch.id), period))
        .scalar_subquery()
    )
    return (
        select(
            col(Branch.code).label("branch_code"),
            col(Branch.name).label("branch_name"),
            (free_units >= quantity).label("available"),
        )
        .where(col(Branch.is_active) == true())
        .order_by(col(Branch.name), col(Branch.code))
    )


def _search_conditions(search: AvailabilitySearch) -> list[ColumnElement[bool]]:
    """Return the model conditions of a search, narrowed to a branch when it names one."""
    conditions = model_conditions(search.models)
    if search.branch_code is not None:
        branch = aliased(Branch)
        branch_id = (
            select(col(branch.id))
            .where(col(branch.code) == search.branch_code, col(branch.is_active) == true())
            .scalar_subquery()
        )
        conditions.append(
            exists(
                select(col(Asset.id)).where(
                    *_free_unit_conditions(col(ProductModel.id), branch_id, search.period)
                )
            )
        )
    return conditions


class SearchAvailabilityQuery:
    """Answers where the fleet is free, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def search(self, search: AvailabilitySearch) -> AvailabilityPage:
        """Answer for every model on one page and every active branch.

        Two statements whatever the page holds, the count and the page.
        """
        filters = {
            **search_filters(search.models),
            "period": search.period.as_postgres_daterange(),
            "branch": search.branch_code,
        }
        with logged_query(logger, "availability.search", filters) as outcome:
            total = int(self._session.execute(availability_count_statement(search)).scalar_one())
            rows = self._session.execute(availability_page_statement(search)).mappings().all()
            outcome.row_count = len(rows)
        items: list[ModelAvailability] = []
        # The statement orders by the sort of the search and ends on the SKU,
        # so the rows of one model are always next to each other.
        for _sku, group in groupby(rows, key=lambda row: row["sku"]):
            model_rows = list(group)
            items.append(
                ModelAvailability(
                    model=summary_of(model_rows[0]),
                    branches=tuple(
                        _branch_availability_of(row)
                        for row in model_rows
                        if row["branch_code"] is not None
                    ),
                )
            )
        return AvailabilityPage(
            period=search.period,
            items=tuple(items),
            page=search.models.page,
            page_size=search.models.page_size,
            total=total,
        )

    def for_model(
        self, model_slug: str, period: BookingPeriod, quantity: int
    ) -> list[BranchAvailability]:
        """Answer for one published model at every active branch, in one statement."""
        filters = {
            "slug": model_slug,
            "period": period.as_postgres_daterange(),
            "quantity": quantity,
        }
        statement = model_availability_statement(model_slug, period, quantity)
        with logged_query(logger, "availability.model_search", filters) as outcome:
            rows = self._session.execute(statement).mappings().all()
            outcome.row_count = len(rows)
        return [_branch_availability_of(row) for row in rows]


def _branch_availability_of(row: RowMapping) -> BranchAvailability:
    """Return the answer of one branch from a row that carries one."""
    return BranchAvailability(
        branch_code=row["branch_code"],
        branch_name=row["branch_name"],
        available=bool(row["available"]),
    )
