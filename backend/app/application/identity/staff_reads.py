"""The read of the staff accounts an administrator lists (FR-25, US-35).

`ReadStaff` is the service the route calls. It refuses a list asked for by a
customer's role, naming the parameter, because a customer is kept through
their profile and the list holds staff only, and it says what it was asked
for and what it found. The page and the text have already been held to their
ranges by the API, and once more by `StaffSearch`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from app.application.identity.staff_read_models import StaffDirectory, StaffPage, StaffSearch
from app.application.refusal import refused
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.domain.staff_account import NOT_A_STAFF_ROLE_MESSAGE, ROLE, STAFF_ROLES

logger = logging.getLogger(__name__)

ROLE_PARAMETER: Final[str] = ROLE


@dataclass(frozen=True, slots=True)
class StaffListRequest:
    """What the administrator asked the list of staff for.

    Attributes:
        actor: The administrator reading it.
        text: Part of a name or an address, or None.
        role: Only accounts in this role, or None for both staff roles.
        active: Only active accounts, only deactivated ones, or None for both.
        page: The page, counted from one.
        page_size: How many a page holds.

    """

    actor: Actor
    text: str | None
    role: UserRole | None
    active: bool | None
    page: int
    page_size: int


class ReadStaff:
    """Reads the staff accounts for an administrator."""

    def __init__(self, directory: StaffDirectory) -> None:
        """Keep the query object the accounts are read through."""
        self._directory = directory

    def page(self, request: StaffListRequest) -> StaffPage:
        """Return one page of the staff accounts that match, by name.

        Raises:
            ValidationFailure: Naming `role`, when it is the customer's.

        """
        logger.info(
            "staff.list_requested",
            extra={
                "actor_user_id": str(request.actor.user_id),
                "text_length": len(request.text) if request.text is not None else 0,
                "role": request.role.value if request.role is not None else None,
                "active": request.active,
                "page": request.page,
                "page_size": request.page_size,
            },
        )
        if request.role is not None and request.role not in STAFF_ROLES:
            raise refused(ROLE_PARAMETER, NOT_A_STAFF_ROLE_MESSAGE, {"role": request.role.value})
        found = self._directory.page(
            StaffSearch(
                text=request.text,
                role=request.role,
                active=request.active,
                page=request.page,
                page_size=request.page_size,
            )
        )
        logger.info(
            "staff.list_read",
            extra={"row_count": len(found.items), "total": found.total, "page": found.page},
        )
        return found
