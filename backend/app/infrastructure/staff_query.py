"""The staff accounts as a query object, by name (FR-25, US-35).

A page is two statements however long the page is, the count and the page,
and one account is one statement by its key. Every statement holds the staff
condition the partial index `ix_user_account_staff` of revision 0011 was built
with, so the accounts are read off that index, which holds the staff and none
of the customers, whose accounts are almost every row of `user_account`. The
page is read in the order of the index, by name and then by key. The branch of
counter staff is joined by its key for its code, and an administrator has
none.

A role and whether the account is active narrow the rows the index gives.
Part of a name or an address is matched case blind anywhere in either, as a
bound value with the two LIKE wildcards and the backslash taken out first, so
a search for `%` finds nobody. The staff of a hire business are a few dozen
people, so every condition is answered from a few dozen index entries.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_
from sqlmodel import Session, col, select
from sqlmodel.sql.expression import Select

from app.application.identity.staff_read_models import StaffMember, StaffPage, StaffSearch
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.customer_search import ANY_TEXT, LIKE_SPECIALS
from app.infrastructure.models import Branch, UserAccount
from app.infrastructure.query_log import logged_query
from app.infrastructure.staff_accounts import role_condition, staff_condition

logger = logging.getLogger(__name__)

CREATED_AT_COLUMN: Final[str] = "user_account.created_at"

# One staff account as a statement reads it, with the code of its branch. The
# join to the branch is an outer one, so for an administrator the code is null,
# whatever the column type says.
type _StaffRow = tuple[UserAccount, str]


def _conditions(search: StaffSearch) -> list[ColumnElement[bool]]:
    """Return the conditions a staff account has to meet, the staff condition first."""
    conditions = [staff_condition()]
    if search.role is not None:
        conditions.append(role_condition(search.role))
    if search.active is not None:
        conditions.append(col(UserAccount.is_active) == search.active)
    text = search.text.translate(LIKE_SPECIALS).strip() if search.text is not None else None
    if text:
        pattern = f"{ANY_TEXT}{text}{ANY_TEXT}"
        conditions.append(
            or_(col(UserAccount.full_name).ilike(pattern), col(UserAccount.email).ilike(pattern))
        )
    elif search.text is not None:
        # Nothing is left of the text once the wildcards are out, so it matches nobody.
        conditions.append(col(UserAccount.id).is_(None))
    return conditions


def _member_statement() -> Select[_StaffRow]:
    """Return the statement every staff account is read with, before it is narrowed."""
    return select(UserAccount, col(Branch.code)).outerjoin(
        Branch, col(Branch.id) == col(UserAccount.branch_id)
    )


class SqlStaffDirectory:
    """Reads the staff accounts through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the request."""
        self._session = session

    def page(self, search: StaffSearch) -> StaffPage:
        """Return one page of the staff accounts that match, by name, in two statements."""
        conditions = _conditions(search)
        filters: dict[str, object] = {
            "text_length": len(search.text) if search.text is not None else 0,
            "role": search.role.value if search.role is not None else None,
            "active": search.active,
            "page": search.page,
            "page_size": search.page_size,
        }
        with logged_query(logger, "staff.directory_page", filters) as outcome:
            total = self._session.exec(
                select(func.count()).select_from(UserAccount).where(*conditions)
            ).one()
            rows = self._session.exec(
                _member_statement()
                .where(*conditions)
                .order_by(func.lower(col(UserAccount.full_name)), col(UserAccount.id))
                .offset(search.offset)
                .limit(search.page_size)
            ).all()
            outcome.row_count = len(rows)
        return StaffPage(
            items=tuple(_member_of(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def one(self, user_id: UUID) -> StaffMember | None:
        """Return one staff account, or None when no staff account has this key."""
        statement = _member_statement().where(
            staff_condition(), col(UserAccount.id) == user_id
        )
        with logged_query(
            logger, "staff.directory_one", {"user_id": str(user_id)}
        ) as outcome:
            found = self._session.exec(statement.execution_options(populate_existing=True)).first()
            outcome.row_count = 0 if found is None else 1
        return _member_of(found) if found is not None else None


def _member_of(row: _StaffRow) -> StaffMember:
    """Return one staff account as a read model."""
    account, branch_code = row
    verified_at: datetime | None = account.email_verified_at
    return StaffMember(
        id=account.id,
        email=account.email,
        full_name=account.full_name,
        phone=account.phone,
        role=account.role,
        branch_code=branch_code if account.branch_id is not None else None,
        is_active=account.is_active,
        email_verified=verified_at is not None,
        last_login_at=in_utc(account.last_login_at),
        locked_until=in_utc(account.locked_until),
        created_at=required_utc(account.created_at, CREATED_AT_COLUMN),
    )
