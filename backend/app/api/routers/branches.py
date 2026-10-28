"""The branch directory endpoint.

Public by declaration. A visitor chooses a branch before there is any account
to sign in to, so the three trading branches are listed for anyone who asks.
The response carries where a branch is and when its counter is open, and
nothing about its stock or its staff.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from app.api.catalogue_deps import BranchDirectoryDependency, cache_briefly
from app.api.catalogue_schemas import (
    BranchListResponse,
    BranchResponse,
    ClosedDayResponse,
    OpeningHoursResponse,
)
from app.api.deps import ClockDependency, public_access
from app.application.identity.read_models import BranchListing
from app.domain.period import MAXIMUM_DAYS_AHEAD, MAXIMUM_HIRE_DAYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/branches", tags=["branches"], dependencies=[Depends(public_access)])


@router.get(
    "",
    response_model=BranchListResponse,
    summary="List the trading branches",
    dependencies=[Depends(cache_briefly)],
)
def list_branches(
    branches: BranchDirectoryDependency, clock: ClockDependency
) -> BranchListResponse:
    """Return every active branch, ordered by name, with its days and hours."""
    listings = branches.list_active()
    today = clock.today()
    logger.debug("branches.listed", extra={"branch_count": len(listings)})
    return BranchListResponse(items=[_response_of(listing, today) for listing in listings])


def _response_of(listing: BranchListing, today: date) -> BranchResponse:
    """Spell one branch, its week and its closed days through the booking horizon."""
    calendar = listing.calendar
    last_day = today + timedelta(days=MAXIMUM_DAYS_AHEAD + MAXIMUM_HIRE_DAYS)
    return BranchResponse(
        code=listing.code,
        name=listing.name,
        suburb=listing.suburb,
        city=listing.city,
        phone=listing.phone,
        weekly_hours=[
            OpeningHoursResponse(weekday=weekday, opens_at=hours.opens, closes_at=hours.closes)
            for weekday, hours in sorted(calendar.weekly.items())
        ],
        closed_days=[
            ClosedDayResponse(day=closed.day, reason=closed.reason, kind=closed.kind)
            for closed in calendar.closed_days_between(today, last_day)
        ],
    )
