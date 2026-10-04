"""The administrator's list of customers by standing, as a query object (BR-18, US-35).

A page is two statements however long the page is, the count and the page,
and each customer is the `CustomerSummary` the counter's lookup reads, from
the same statement. The page is in name order and then by key.

1. With no standing named, the page is read in the order of
   `ix_customer_profile_name` of revision 0011 and stops at the end of the
   page, and the count reads that index from end to end.
2. ON_HOLD and BLACKLISTED are written into the statement with the predicate
   of `ix_customer_profile_standing`, `account_status <> 'ACTIVE'`, as the
   literal it was built with, so the planner reads the customers out of good
   standing, which the screen is for, out of an index that holds nobody else.
   The count and the page both stand on it.
3. ACTIVE is almost every customer, so its page is read in name order like
   the first and its count reads every customer in good standing.
4. A text is matched the way the counter matches one, by part of a name, the
   digits of a phone number or the address of an account, each through its
   trigram or unique index, and the standing then narrows what was found.

The text is never placed in a statement as SQL, and it is logged by its length
only.
"""

from __future__ import annotations

import logging

from sqlalchemy import ColumnElement, func, literal_column
from sqlmodel import Session, col, select

from app.application.identity.customer_directory import CustomerPage
from app.application.identity.customer_listing import CustomerListSearch
from app.domain.enums import AccountStatus
from app.infrastructure.customer_search import (
    matching_condition,
    search_terms,
    summary_of,
    summary_statement,
)
from app.infrastructure.models import CustomerProfile
from app.infrastructure.query_log import logged_query
from app.infrastructure.schema_ddl import GOOD_STANDING_LITERAL

logger = logging.getLogger(__name__)


def standing_conditions(status: AccountStatus) -> list[ColumnElement[bool]]:
    """Return the conditions on a standing, with the index predicate for one out of good standing.

    Each value is written as the literal it is stored as, so a cached plan
    still matches the partial index.
    """
    standing = col(CustomerProfile.account_status)
    wanted = standing == literal_column(f"'{status.value}'")
    if status is AccountStatus.ACTIVE:
        return [wanted]
    return [standing != literal_column(GOOD_STANDING_LITERAL), wanted]


class SqlCustomerListing:
    """Lists the customers by standing through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the request."""
        self._session = session

    def page(self, search: CustomerListSearch) -> CustomerPage:
        """Return one page of the customers that match, by name, in two statements."""
        conditions = standing_conditions(search.status) if search.status is not None else []
        filters: dict[str, object] = {
            "status": search.status.value if search.status is not None else None,
            "text_length": len(search.text) if search.text is not None else 0,
            "page": search.page,
            "page_size": search.page_size,
        }
        if search.text is not None:
            matched = matching_condition(search_terms(search.text))
            if matched is None:
                logger.info("identity.customer_list_skipped", extra=filters)
                return CustomerPage(
                    items=(), page=search.page, page_size=search.page_size, total=0
                )
            conditions.append(matched)
        with logged_query(logger, "identity.customer_list", filters) as outcome:
            total = self._session.exec(
                select(func.count()).select_from(CustomerProfile).where(*conditions)
            ).one()
            found = self._session.exec(
                summary_statement()
                .where(*conditions)
                .order_by(func.lower(col(CustomerProfile.display_name)), col(CustomerProfile.id))
                .offset(search.offset)
                .limit(search.page_size)
            ).all()
            outcome.row_count = len(found)
        return CustomerPage(
            items=tuple(summary_of(row) for row in found),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )
