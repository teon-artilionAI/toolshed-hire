"""The customer directory, which is how the counter finds a customer (US-21).

A counter assistant looks a customer up by part of their name, by their phone
number or by the email address of their account, picks one and books for
them. `CustomerDirectory` is the port that answers, and it returns the small
frozen dataclasses of this module and never a table row.

`CustomerSummary` is a customer as the counter sees one. It carries what the
assistant needs to be sure they have the right person and whether that person
may book, which is the last four characters of their identity document, the
suburb they bill to and the standing of their account. It carries no full
address and no document number, because the counter never needs either.

A search is bounded. The text is two to eighty characters and a page holds at
most fifty customers, so no request can ask the database for every profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol
from uuid import UUID

from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.domain.enums import AccountStatus, CustomerType, IdDocType

MINIMUM_CUSTOMER_SEARCH_LENGTH: Final[int] = 2
MAXIMUM_CUSTOMER_SEARCH_LENGTH: Final[int] = 80


@dataclass(frozen=True, slots=True)
class CustomerSummary:
    """A customer as the counter sees one.

    Attributes:
        id: The customer profile key, which a counter booking names.
        display_name: The name staff see.
        email: The address of the customer's account, or None for a walk-in.
        phone: The number the branch can reach them on.
        has_login: True when the customer has a sign in account.
        email_verified: True when that account has proved its address.
        customer_type: Whether they hire as an individual or as a trade.
        company_name: The company of a trade customer.
        id_document_type: The kind of identity document on file.
        id_document_last4: Its last four characters.
        billing_suburb: The suburb they bill to.
        billing_city: The city they bill to.
        account_status: Their standing (BR-18).
        trade_discount_percent: The discount a trade customer is given.
        no_show_count: How many bookings they did not collect.
        home_branch_code: The code of the branch that registered them.

    """

    id: UUID
    display_name: str
    email: str | None
    phone: str
    has_login: bool
    email_verified: bool
    customer_type: CustomerType
    company_name: str | None
    id_document_type: IdDocType
    id_document_last4: str
    billing_suburb: str
    billing_city: str
    account_status: AccountStatus
    trade_discount_percent: Decimal
    no_show_count: int
    home_branch_code: str


@dataclass(frozen=True, slots=True)
class CustomerSearch:
    """What the counter typed, and which page of the answer it wants.

    Attributes:
        text: The text to match, without surrounding space.
        page: The page wanted, counted from one.
        page_size: How many customers a page holds.

    """

    text: str
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary checks the same limits and answers with a 422. This
        is the second line, so a caller inside the system cannot ask for every
        profile at once.

        Raises:
            ValueError: If the text, the page or the page size is out of range.

        """
        if not MINIMUM_CUSTOMER_SEARCH_LENGTH <= len(self.text) <= MAXIMUM_CUSTOMER_SEARCH_LENGTH:
            raise ValueError(
                f"Attempted to search customers with {len(self.text)} characters. A search "
                f"has between {MINIMUM_CUSTOMER_SEARCH_LENGTH} and "
                f"{MAXIMUM_CUSTOMER_SEARCH_LENGTH}."
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
        """Return how many customers come before the page wanted."""
        return (self.page - FIRST_PAGE) * self.page_size


@dataclass(frozen=True, slots=True)
class CustomerPage:
    """One page of the customers a search found, best match first."""

    items: tuple[CustomerSummary, ...]
    page: int
    page_size: int
    total: int


class CustomerDirectory(Protocol):
    """Where the counter finds a customer."""

    def search(self, search: CustomerSearch) -> CustomerPage:
        """Return one page of the customers whose name, phone or email the text matches.

        The best match comes first. An exact phone number or email address
        comes before a name that starts with the text, which comes before a
        name with a word that starts with it, which comes before any other
        name that contains it.
        """
        ...

    def summary(self, customer_profile_id: UUID) -> CustomerSummary | None:
        """Return one customer, or None when there is no profile with this key."""
        ...
