"""The asset register as the administrator reads it (FR-23, US-31, SC-21).

The administrator lists every unit of the fleet, retired or not, narrowed by
branch, status and model and searched by part of the tag, the serial number or
the model name, and reads one unit with its history. Nothing here writes, so
there is no unit of work and no audit event. The reads go through the
`AssetRegisterQuery` port, and the rules that are not SQL live here, that a
branch nobody knows is refused by name, that a tag nobody carries is a 404,
and how the history is put together.

A retired unit keeps its row, so it is listed and read like any other, with
its whole history (BR-38).

The search text is logged by its length only, as every search is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.admin_lists import DEFAULT_PAGE_SIZE, FIRST_PAGE
from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.catalogue.asset_history import HISTORY_LIMIT, history_of
from app.application.catalogue.asset_ports import AssetRegisterQuery
from app.application.catalogue.asset_read_models import (
    AdminAssetDetail,
    AdminAssetPage,
    AdminAssetSearch,
)
from app.application.hire.list_rentals import BRANCH_CODE_PARAMETER
from app.application.refusal import refused
from app.domain.enums import AssetStatus
from app.domain.errors import NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

NO_TEXT: Final[int] = 0
UNIT_NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find a unit with that tag. Check the tag and try again."
)


@dataclass(frozen=True, slots=True)
class ListUnitsQuery:
    """Which units an administrator wants listed.

    Attributes:
        text: Part of the tag, the serial number or the model name, or None.
        branch_code: Only the units of the branch with this code, or None.
        status: Only the units in this status, or None.
        model_id: Only the units of this model, or None.
        page: The page, counted from one.
        page_size: How many units a page holds.

    """

    text: str | None = None
    branch_code: str | None = None
    status: AssetStatus | None = None
    model_id: UUID | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE


def unit_detail(register: AssetRegisterQuery, asset_tag: str) -> AdminAssetDetail:
    """Return one unit with its history, read through the query object.

    Raises:
        NotFound: If no unit carries the tag.

    """
    entry = register.unit(asset_tag)
    if entry is None:
        logger.info("asset.register_unit_not_found", extra={"asset_tag": asset_tag})
        raise NotFound(UNIT_NOT_FOUND_MESSAGE, {"asset_tag": asset_tag})
    history = history_of(register.history(entry.id, HISTORY_LIMIT), HISTORY_LIMIT)
    return AdminAssetDetail(entry=entry, history=history)


class ReadAssetRegister:
    """Reads the asset register for an administrator."""

    def __init__(self, register: AssetRegisterQuery) -> None:
        """Keep the query object the register is read through."""
        self._register = register

    def page(self, actor: Actor, query: ListUnitsQuery) -> AdminAssetPage:
        """Return one page of the units that match, in tag order.

        Raises:
            ValidationFailure: Naming `branchCode` when no branch has the code.

        """
        logger.info(
            "asset.register_list_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "q_length": len(query.text) if query.text is not None else NO_TEXT,
                "branch_code": query.branch_code,
                "status": query.status.value if query.status else None,
                "model_id": str(query.model_id) if query.model_id else None,
                "page": query.page,
                "page_size": query.page_size,
            },
        )
        search = AdminAssetSearch(
            text=query.text,
            branch_id=self._branch_id_of(query.branch_code),
            status=query.status,
            model_id=query.model_id,
            page=query.page,
            page_size=query.page_size,
        )
        found = self._register.page(search)
        logger.info(
            "asset.register_list_read",
            extra={"row_count": len(found.items), "total": found.total, "page": found.page},
        )
        return found

    def unit(self, actor: Actor, asset_tag: str) -> AdminAssetDetail:
        """Return one unit with its history, the newest first.

        Raises:
            NotFound: If no unit carries the tag.

        """
        logger.info(
            "asset.register_unit_requested",
            extra={"actor_user_id": str(actor.user_id), "asset_tag": asset_tag},
        )
        detail = unit_detail(self._register, asset_tag)
        logger.info(
            "asset.register_unit_read",
            extra={
                "asset_tag": detail.entry.asset_tag,
                "status": detail.entry.status.value,
                "history_entries": len(detail.history),
            },
        )
        return detail

    def _branch_id_of(self, branch_code: str | None) -> UUID | None:
        """Return the key of the branch a list is narrowed to, or None.

        Raises:
            ValidationFailure: Naming `branchCode` when no branch has the code.

        """
        if branch_code is None:
            return None
        branch_id = self._register.branch_id_of(branch_code)
        if branch_id is None:
            logger.info("asset.register_branch_unknown", extra={"branch_code": branch_code})
            raise refused(BRANCH_CODE_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
        return branch_id
