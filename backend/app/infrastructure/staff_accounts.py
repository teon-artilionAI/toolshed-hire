"""The SQL side of the staff accounts the administrator writes (FR-25, US-35).

The lock on every active administrator is one statement. It reads the staff
accounts through `ix_user_account_staff` of revision 0011, which holds no
customer's account, keeps the active administrators and locks them with
`FOR UPDATE` in the order of their keys. Every transaction that changes a
staff account asks for the same rows in the same order, so of two at once the
second waits for the first and never holds a row the first is waiting for.
When it is let through, PostgreSQL reads each row it waited for again and
drops one that is no longer an active administrator, so the set it answers
with is what the first transaction committed.

`save_staff` writes the five fields an administrator decides on to a row the
use case has already loaded and locked. The check constraint
`ck_user_account_branch_scope` has the last word on a role and a branch.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import ColumnElement, literal_column, true
from sqlmodel import Session, col, select

from app.domain.account import Account
from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from app.infrastructure.schema_ddl import CUSTOMER_ROLE_LITERAL

logger = logging.getLogger(__name__)


def staff_condition() -> ColumnElement[bool]:
    """Return the condition that an account is a staff account, as the index predicate reads.

    It is written as the literal the partial index `ix_user_account_staff`
    was built with, so the planner can match the predicate in any plan.
    """
    return col(UserAccount.role) != literal_column(CUSTOMER_ROLE_LITERAL)


def role_condition(role: UserRole) -> ColumnElement[bool]:
    """Return the condition on one role, written as the literal it is stored as."""
    return col(UserAccount.role) == literal_column(f"'{role.value}'")


class SqlStaffRepository:
    """Locks the administrators and writes staff accounts through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def lock_active_administrators(self) -> frozenset[UUID]:
        """Return every active administrator, locked in the order of their keys."""
        statement = (
            select(UserAccount.id)
            .where(
                staff_condition(),
                role_condition(UserRole.ADMIN),
                col(UserAccount.is_active) == true(),
            )
            .order_by(col(UserAccount.id))
            .with_for_update()
        )
        administrators = frozenset(self._session.exec(statement).all())
        logger.debug("staff.administrators_locked", extra={"count": len(administrators)})
        return administrators

    def save_staff(self, account: Account) -> None:
        """Write the name, the phone, the role, the branch and whether the account is active.

        Raises:
            RuntimeError: If the account has no row, which would mean a use
                case is saving an account it never loaded.

        """
        row = self._session.get(UserAccount, account.id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save staff account {account.id}, which has no row. Load the "
                "account through the account repository before saving it."
            )
        row.full_name = account.full_name
        row.phone = account.phone
        row.role = account.role
        row.branch_id = account.branch_id
        row.is_active = account.is_active
        self._session.add(row)
        self._session.flush()
        logger.info(
            "staff.account_saved",
            extra={
                "user_id": str(account.id),
                "role": account.role.value,
                "is_active": account.is_active,
            },
        )
