"""The dependencies of the counter overview, which are the dashboard, the diary and the locator.

This is the counter's part of the composition root. The three are reads, so
each query object is handed the request scoped session and the request closes
it, the way the catalogue's read side is wired in `app/api/catalogue_deps.py`.
The dashboard and the diary are also handed the sweep from
`app/api/sweep_deps.py` and run it before they answer (BR-13, BR-17), and the
branch repository, through which they find the branch they are asked about.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, SessionDependency
from app.api.sweep_deps import ExpiredHoldSweeper
from app.application.catalogue.locator import AssetLocatorQuery, LocateAssets
from app.application.hire.overview import ReadCounterOverview
from app.application.hire.ports import CounterOverviewQuery
from app.infrastructure.asset_locator import SqlAssetLocator
from app.infrastructure.branch_repository import SqlBranchRepository
from app.infrastructure.counter_overview import SqlCounterOverview


def get_counter_overview_query(session: SessionDependency) -> CounterOverviewQuery:
    """Return the SQL counter overview over the request scoped session."""
    return SqlCounterOverview(session)


CounterOverviewQueryDependency = Annotated[
    CounterOverviewQuery, Depends(get_counter_overview_query)
]


def get_read_counter_overview(
    overview: CounterOverviewQueryDependency,
    session: SessionDependency,
    clock: ClockDependency,
    lapse_due_bookings: ExpiredHoldSweeper,
) -> ReadCounterOverview:
    """Return the dashboard and the diary, wired to their query object, the clock and the sweep."""
    return ReadCounterOverview(overview, SqlBranchRepository(session), clock, lapse_due_bookings)


ReadCounterOverviewDependency = Annotated[
    ReadCounterOverview, Depends(get_read_counter_overview)
]


def get_asset_locator(session: SessionDependency) -> AssetLocatorQuery:
    """Return the SQL asset locator over the request scoped session."""
    return SqlAssetLocator(session)


AssetLocatorDependency = Annotated[AssetLocatorQuery, Depends(get_asset_locator)]


def get_locate_assets(locator: AssetLocatorDependency) -> LocateAssets:
    """Return the asset locator, wired to its query object."""
    return LocateAssets(locator)


LocateAssetsDependency = Annotated[LocateAssets, Depends(get_locate_assets)]
