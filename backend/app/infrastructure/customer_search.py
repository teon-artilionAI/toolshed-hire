"""The counter's customer lookup, as a query object over one session (US-21).

A search is matched three ways and every way stands on an index.

1. Part of the display name, case blind, anywhere in it. The trigram index
   `ix_customer_profile_display_name_trgm` serves `ILIKE '%text%'`.
2. The digits of the contact phone, when the text looks like a phone number.
   The spaces, hyphens, brackets and plus sign a number may carry are taken
   out of both sides, so `0824417719` finds `082 441 7719`. The trigram index
   `ix_customer_profile_phone_digits_trgm` of revision 0003 is built over
   exactly the expression `phone_digits` writes here.
3. The email address of the customer's account, exactly and case blind, when
   the text holds an `@`. The unique index on the address finds the account
   and the unique index on `customer_profile.user_account_id` finds its
   profile. A walk-in has no account and is never found this way.

The three are joined with OR on the one table, so the planner can answer each
with its own index and combine them, and the count and the page run the same
condition. The best match comes first. An exact phone number or email address
ranks first, then a name that starts with the text, then a name with a word
that starts with it, then any other name that holds it. The name breaks a tie
and then the key, so the order is the same on every call.

The text is never placed in a statement as SQL. It travels as a bound value,
with the two LIKE wildcards and the backslash taken out first, so a search for
`%` cannot match every customer. Only the constant punctuation of the phone
expression is written as literal text, because a bound value there would stop
a cached plan from matching the index.

What degrades first as the profiles grow is a two character name search. A
trigram index cannot narrow a pattern shorter than three characters, so `al`
reads the whole index and then sorts every match to find the first page. Three
or more characters stay cheap. The page is found with OFFSET, so a deep page
reads every match before it, which is why a page is at most fifty and the
counter is expected to type more rather than page on.
"""

from __future__ import annotations

import logging
import string
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, String, case, func, literal_column, or_
from sqlalchemy.orm import Mapped
from sqlmodel import Session, col, select
from sqlmodel.sql.expression import Select

from app.application.identity.customer_directory import (
    CustomerPage,
    CustomerSearch,
    CustomerSummary,
)
from app.infrastructure.models import Branch, CustomerProfile, UserAccount
from app.infrastructure.query_log import logged_query
from app.infrastructure.schema_ddl import PHONE_PUNCTUATION_REMOVED

logger = logging.getLogger(__name__)

# One row of the statement that reads a summary. The profile, the address and
# the verification of its account, and the code of its branch. The join to the
# account is an outer one, so for a walk-in the two account columns are null,
# whatever the column types say.
type _Found = tuple[CustomerProfile, str, datetime | None, str]

# The two LIKE wildcards and the escape character, which a search text loses.
LIKE_SPECIALS: Final[dict[int, int | None]] = str.maketrans("", "", "%_\\")
ANY_TEXT: Final[str] = "%"
WORD_START: Final[str] = " "
EMAIL_MARK: Final[str] = "@"
EMPTY_TEXT_LITERAL: Final[str] = "''"
# A trigram index needs three characters to narrow a search by.
MINIMUM_PHONE_DIGITS: Final[int] = 3
PHONE_CHARACTERS: Final[frozenset[str]] = frozenset(string.digits).union(
    PHONE_PUNCTUATION_REMOVED
)
EXACT_MATCH_RANK: Final[int] = 0
NAME_START_RANK: Final[int] = 1
WORD_START_RANK: Final[int] = 2
ANY_MATCH_RANK: Final[int] = 3


@dataclass(frozen=True, slots=True)
class SearchTerms:
    """What a search text is matched with, one value for each way it can match.

    Attributes:
        name: The text to find in a name, or None when nothing is left of it.
        phone_digits: The digits to find in a phone number, or None when the
            text is not shaped like one.
        email: The address to find exactly, or None when the text holds no `@`.

    """

    name: str | None
    phone_digits: str | None
    email: str | None


def search_terms(text: str) -> SearchTerms:
    """Return the values a search text is matched with."""
    name = text.translate(LIKE_SPECIALS).strip()
    digits = "".join(character for character in text if character in string.digits)
    shaped_like_a_phone = set(text) <= PHONE_CHARACTERS and len(digits) >= MINIMUM_PHONE_DIGITS
    return SearchTerms(
        name=name or None,
        phone_digits=digits if shaped_like_a_phone else None,
        email=text.lower() if EMAIL_MARK in text else None,
    )


def phone_digits(phone: Mapped[str]) -> ColumnElement[str]:
    """Return the digits of a phone column, written exactly as the index of revision 0003.

    The punctuation is removed one character at a time, innermost first, in
    the order the migration removes it.
    """
    first, *rest = PHONE_PUNCTUATION_REMOVED
    expression = _without(phone, first)
    for character in rest:
        expression = _without(expression, character)
    return expression


def _without(text: ColumnElement[str] | Mapped[str], character: str) -> ColumnElement[str]:
    """Return a text expression with every copy of one character removed from it.

    The character is written into the statement as a literal and not bound,
    because the expression has to match the index for any plan the database
    caches. Every character it is called with is a constant of this module.
    """
    return func.replace(
        text, literal_column(f"'{character}'"), literal_column(EMPTY_TEXT_LITERAL), type_=String
    )


def matching_condition(terms: SearchTerms) -> ColumnElement[bool] | None:
    """Return the condition a profile has to meet to be found, or None when nothing can be."""
    arms: list[ColumnElement[bool]] = []
    if terms.name is not None:
        arms.append(col(CustomerProfile.display_name).ilike(f"{ANY_TEXT}{terms.name}{ANY_TEXT}"))
    if terms.phone_digits is not None:
        arms.append(
            phone_digits(col(CustomerProfile.contact_phone)).like(
                f"{ANY_TEXT}{terms.phone_digits}{ANY_TEXT}"
            )
        )
    if terms.email is not None:
        arms.append(_holds_the_account_of(terms.email))
    return or_(*arms) if arms else None


def _holds_the_account_of(email: str) -> ColumnElement[bool]:
    """Return the condition that a profile belongs to the account with this address."""
    account = select(col(UserAccount.id)).where(col(UserAccount.email) == email)
    return col(CustomerProfile.user_account_id) == account.scalar_subquery()


def _rank(terms: SearchTerms) -> ColumnElement[int]:
    """Return how well a found profile matches, the best being the lowest."""
    exact: list[ColumnElement[bool]] = []
    if terms.phone_digits is not None:
        exact.append(phone_digits(col(CustomerProfile.contact_phone)) == terms.phone_digits)
    if terms.email is not None:
        exact.append(_holds_the_account_of(terms.email))
    whens: list[tuple[ColumnElement[bool], int]] = []
    if exact:
        whens.append((or_(*exact), EXACT_MATCH_RANK))
    if terms.name is not None:
        name = col(CustomerProfile.display_name)
        whens.append((name.ilike(f"{terms.name}{ANY_TEXT}"), NAME_START_RANK))
        whens.append((name.ilike(f"{ANY_TEXT}{WORD_START}{terms.name}{ANY_TEXT}"), WORD_START_RANK))
    return case(*whens, else_=ANY_MATCH_RANK)


class SqlCustomerDirectory:
    """Finds customers for the counter through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the directory to the session of the unit of work."""
        self._session = session

    def search(self, search: CustomerSearch) -> CustomerPage:
        """Return one page of the customers whose name, phone or email the text matches."""
        terms = search_terms(search.text)
        condition = matching_condition(terms)
        filters: dict[str, object] = {
            "text_length": len(search.text),
            "by_name": terms.name is not None,
            "by_phone": terms.phone_digits is not None,
            "by_email": terms.email is not None,
            "page": search.page,
            "page_size": search.page_size,
        }
        if condition is None:
            logger.info("identity.customer_search_skipped", extra=filters)
            return CustomerPage(items=(), page=search.page, page_size=search.page_size, total=0)
        count_statement = select(func.count()).select_from(CustomerProfile).where(condition)
        page_statement = (
            _summary_statement()
            .where(condition)
            .order_by(
                _rank(terms),
                func.lower(col(CustomerProfile.display_name)),
                col(CustomerProfile.id),
            )
            .limit(search.page_size)
            .offset(search.offset)
        )
        with logged_query(logger, "identity.customer_search", filters) as outcome:
            total = self._session.exec(count_statement).one()
            found = self._session.exec(page_statement).all()
            outcome.row_count = len(found)
        return CustomerPage(
            items=tuple(_summary_of(row) for row in found),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def summary(self, customer_profile_id: UUID) -> CustomerSummary | None:
        """Return one customer, or None when there is no profile with this key."""
        statement = _summary_statement().where(col(CustomerProfile.id) == customer_profile_id)
        with logged_query(
            logger, "identity.customer_summary", {"customer_profile_id": str(customer_profile_id)}
        ) as outcome:
            found = self._session.exec(statement).first()
            outcome.row_count = 0 if found is None else 1
        return _summary_of(found) if found is not None else None


def _summary_statement() -> Select[_Found]:
    """Return the statement every summary is read with, before it is narrowed.

    The join to the account is an outer one, because a walk-in has a profile
    and no account.
    """
    return (
        select(
            CustomerProfile,
            col(UserAccount.email),
            col(UserAccount.email_verified_at),
            col(Branch.code),
        )
        .outerjoin(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
        .join(Branch, col(Branch.id) == col(CustomerProfile.registered_branch_id))
    )


def _summary_of(found: _Found) -> CustomerSummary:
    """Return the summary of one found profile."""
    profile, email, email_verified_at, branch_code = found
    has_login = profile.user_account_id is not None
    return CustomerSummary(
        id=profile.id,
        display_name=profile.display_name,
        email=email if has_login else None,
        phone=profile.contact_phone,
        has_login=has_login,
        email_verified=email_verified_at is not None,
        customer_type=profile.customer_type,
        company_name=profile.company_name,
        id_document_type=profile.id_document_type,
        id_document_last4=profile.id_document_last4,
        billing_suburb=profile.billing_suburb,
        billing_city=profile.billing_city,
        account_status=profile.account_status,
        trade_discount_percent=Decimal(profile.trade_discount_percent),
        no_show_count=profile.no_show_count,
        home_branch_code=branch_code,
    )
