"""The customers an administrator lists by their standing (BR-18, US-35).

The administrator keeps the holds and the blacklisting, so the list is
narrowed by `accountStatus` and searched the way the counter searches, by part
of a name, a phone number or the address of an account. Each customer is the
`CustomerSummary` the counter already reads, so the two screens show a
customer the same way.

`CustomerListing` is the port, and its query object returns the small frozen
dataclasses of `customer_directory` and never a table row. A search is
bounded. The text is two to eighty characters when there is one, and a page
holds at most a hundred customers. The text is logged by its length only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.application.admin_lists import (
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
    offset_of,
)
from app.application.identity.customer_directory import (
    MAXIMUM_CUSTOMER_SEARCH_LENGTH,
    MINIMUM_CUSTOMER_SEARCH_LENGTH,
    CustomerPage,
)
from app.domain.enums import AccountStatus
from app.domain.identity import Actor

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CustomerListSearch:
    """Which customers to list, and which page of them.

    Attributes:
        status: Only customers in this standing, or None for every one.
        text: Part of a name, a phone number or an address, or None.
        page: The page, counted from one.
        page_size: How many customers a page holds.

    """

    status: AccountStatus | None
    text: str | None
    page: int
    page_size: int

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        Raises:
            ValueError: If the text, the page or the page size is out of range.

        """
        length = len(self.text) if self.text is not None else MINIMUM_CUSTOMER_SEARCH_LENGTH
        if not MINIMUM_CUSTOMER_SEARCH_LENGTH <= length <= MAXIMUM_CUSTOMER_SEARCH_LENGTH:
            raise ValueError(
                f"Attempted to list customers searching {length} characters. A search has "
                f"between {MINIMUM_CUSTOMER_SEARCH_LENGTH} and {MAXIMUM_CUSTOMER_SEARCH_LENGTH}."
            )
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to list customers for page {self.page}. A page is between "
                f"{FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to list customers with a page size of {self.page_size}. A page "
                f"holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} customers."
            )

    @property
    def offset(self) -> int:
        """Return how many customers come before the first one on the page."""
        return offset_of(self.page, self.page_size)


class CustomerListing(Protocol):
    """The customers, as the administrator lists them by standing."""

    def page(self, search: CustomerListSearch) -> CustomerPage:
        """Return one page of the customers that match, by name and then by key.

        It takes the same number of statements however long the page is.
        """
        ...


@dataclass(frozen=True, slots=True)
class CustomerListRequest:
    """What the administrator asked the list of customers for.

    Attributes:
        actor: The administrator reading it.
        status: Only customers in this standing, or None.
        text: Part of a name, a phone number or an address, or None.
        page: The page, counted from one.
        page_size: How many a page holds.

    """

    actor: Actor
    status: AccountStatus | None
    text: str | None
    page: int
    page_size: int


class ReadCustomerList:
    """Reads the customers for an administrator, by standing."""

    def __init__(self, listing: CustomerListing) -> None:
        """Keep the query object the customers are read through."""
        self._listing = listing

    def page(self, request: CustomerListRequest) -> CustomerPage:
        """Return one page of the customers that match, by name."""
        logger.info(
            "customer.list_requested",
            extra={
                "actor_user_id": str(request.actor.user_id),
                "status": request.status.value if request.status is not None else None,
                "text_length": len(request.text) if request.text is not None else 0,
                "page": request.page,
                "page_size": request.page_size,
            },
        )
        found = self._listing.page(
            CustomerListSearch(
                status=request.status,
                text=request.text,
                page=request.page,
                page_size=request.page_size,
            )
        )
        logger.info(
            "customer.list_read",
            extra={"row_count": len(found.items), "total": found.total, "page": found.page},
        )
        return found
