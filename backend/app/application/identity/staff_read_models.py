"""The staff accounts as the administrator reads them (FR-25, US-35).

`StaffMember` is one staff account as the console shows it, the shape the
contract calls `AdminUser`. It carries who the person is, what they may do and
whether they can sign in, and never anything about a password. A customer's
account is never one, because a customer is kept through their profile.

A search is bounded. The text is two to eighty characters and a page holds at
most a hundred accounts, so no request can ask for every account at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol
from uuid import UUID

from app.application.admin_lists import (
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
    offset_of,
)
from app.domain.enums import UserRole

MINIMUM_STAFF_SEARCH_LENGTH: Final[int] = 2
MAXIMUM_STAFF_SEARCH_LENGTH: Final[int] = 80


@dataclass(frozen=True, slots=True)
class StaffMember:
    """One staff account as the administrator sees it.

    Attributes:
        id: The account key.
        email: The address the person signs in with.
        full_name: Their name.
        phone: Their number, or None.
        role: COUNTER_STAFF or ADMIN.
        branch_code: The code of the branch of counter staff, else None.
        is_active: False once the account has been deactivated.
        email_verified: True when the person has proved the address.
        last_login_at: When they last signed in, or None.
        locked_until: When a lock after failed sign ins ends, or None.
        created_at: When the account was opened.

    """

    id: UUID
    email: str
    full_name: str
    phone: str | None
    role: UserRole
    branch_code: str | None
    is_active: bool
    email_verified: bool
    last_login_at: datetime | None
    locked_until: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StaffSearch:
    """Which staff accounts to list, and which page of them.

    Attributes:
        text: Part of the name or the address, or None for every account.
        role: Only accounts holding this staff role, or None for both.
        active: Only active accounts, only deactivated ones, or None for both.
        page: The page, counted from one.
        page_size: How many accounts a page holds.

    """

    text: str | None
    role: UserRole | None
    active: bool | None
    page: int
    page_size: int

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary checks the same limits and answers with a 422, and
        the read refuses a customer role naming the parameter. This is the
        last line, so a caller inside the system cannot ask for every account.

        Raises:
            ValueError: If the text, the page or the page size is out of range.

        """
        text_length = len(self.text) if self.text is not None else MINIMUM_STAFF_SEARCH_LENGTH
        if not MINIMUM_STAFF_SEARCH_LENGTH <= text_length <= MAXIMUM_STAFF_SEARCH_LENGTH:
            raise ValueError(
                f"Attempted to search staff accounts with {text_length} characters. A search "
                f"has between {MINIMUM_STAFF_SEARCH_LENGTH} and {MAXIMUM_STAFF_SEARCH_LENGTH}."
            )
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to list staff accounts for page {self.page}. A page is between "
                f"{FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to list staff accounts with a page size of {self.page_size}. A "
                f"page holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} accounts."
            )

    @property
    def offset(self) -> int:
        """Return how many accounts come before the first one on the page."""
        return offset_of(self.page, self.page_size)


@dataclass(frozen=True, slots=True)
class StaffPage:
    """One page of the staff accounts, by name, and how many match across every page."""

    items: tuple[StaffMember, ...]
    page: int
    page_size: int
    total: int


class StaffDirectory(Protocol):
    """The staff accounts, as the administrator reads them."""

    def page(self, search: StaffSearch) -> StaffPage:
        """Return one page of the staff accounts that match, by name and then by key.

        It takes the same number of statements however long the page is.
        """
        ...

    def one(self, user_id: UUID) -> StaffMember | None:
        """Return one staff account, or None when no staff account has this key.

        A customer's account is answered with None, as an account nobody
        opened is.
        """
        ...
