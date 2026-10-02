"""The branch directory endpoint.

Public by declaration. A visitor chooses a branch before there is any account
to sign in to, so the three trading branches are listed for anyone who asks.
The response carries where a branch is and when its counter is open, and
nothing about its stock or its staff.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.catalogue_deps import BranchDirectoryDependency, cache_briefly
from app.api.catalogue_schemas import BranchListResponse, BranchResponse
from app.api.deps import public_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/branches", tags=["branches"], dependencies=[Depends(public_access)])


@router.get(
    "",
    response_model=BranchListResponse,
    summary="List the trading branches",
    dependencies=[Depends(cache_briefly)],
)
def list_branches(branches: BranchDirectoryDependency) -> BranchListResponse:
    """Return every active branch, ordered by name."""
    listings = branches.list_active()
    logger.debug("branches.listed", extra={"branch_count": len(listings)})
    return BranchListResponse(
        items=[BranchResponse.model_validate(listing) for listing in listings]
    )
