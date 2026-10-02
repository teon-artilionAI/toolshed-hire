"""The SQL side of the identity module, for branches and customer profiles.

The two repositories map the SQLModel table classes to the small domain
entities a booking needs, and they run on the session of the unit of work that
created them. They read, with one exception. A late cancellation is counted on
the customer profile (BR-16), and the customer repository writes that count.

`SqlBranchDirectory` is the read side. It lists the trading branches for a
visitor and returns read models, never a table row.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, update
from sqlmodel import Session, col, select

from app.application.identity.read_models import BranchListing
from app.domain import identity as domain
from app.infrastructure.models import Branch, CustomerProfile, UserAccount
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

LATE_CANCELLATION_INCREMENT: Final[int] = 1


class SqlBranchRepository:
    """Reads branches through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def get(self, branch_id: UUID) -> domain.Branch | None:
        """Return the branch with this key, or None when there is none."""
        logger.debug("identity.branch_lookup_started", extra={"branch_id": str(branch_id)})
        row = self._session.get(Branch, branch_id)
        logger.debug(
            "identity.branch_lookup_finished",
            extra={"branch_id": str(branch_id), "found": row is not None},
        )
        if row is None:
            return None
        return domain.Branch(id=row.id, code=row.code, name=row.name)

    def find_active_by_code(self, code: str) -> domain.Branch | None:
        """Return the trading branch with this code, or None when there is none."""
        statement = select(Branch).where(col(Branch.code) == code, col(Branch.is_active))
        row = self._session.exec(statement).first()
        logger.debug(
            "identity.branch_code_lookup_finished",
            extra={"branch_code": code, "found": row is not None},
        )
        if row is None:
            return None
        return domain.Branch(id=row.id, code=row.code, name=row.name)


class SqlCustomerRepository:
    """Reads customer profiles, and counts on them, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def profile_for_account(self, user_account_id: UUID) -> domain.CustomerProfile | None:
        """Return the customer profile that belongs to a sign in account."""
        return self._find(
            col(CustomerProfile.user_account_id) == user_account_id,
            {"customer_user_id": str(user_account_id)},
        )

    def get(self, customer_profile_id: UUID) -> domain.CustomerProfile | None:
        """Return the customer profile with this key, or None when there is none."""
        return self._find(
            col(CustomerProfile.id) == customer_profile_id,
            {"customer_profile_id": str(customer_profile_id)},
        )

    def record_late_cancellation(self, customer_profile_id: UUID) -> None:
        """Count one late cancellation on a customer profile (BR-16).

        The count is raised by the database, in one statement, so two
        cancellations at the same moment are both counted.
        """
        self._session.execute(
            update(CustomerProfile)
            .where(col(CustomerProfile.id) == customer_profile_id)
            .values(
                late_cancellation_count=col(CustomerProfile.late_cancellation_count)
                + LATE_CANCELLATION_INCREMENT
            )
        )
        logger.info(
            "identity.late_cancellation_recorded",
            extra={"customer_profile_id": str(customer_profile_id)},
        )

    def _find(
        self, condition: ColumnElement[bool], sought: dict[str, str]
    ) -> domain.CustomerProfile | None:
        """Return the one profile a condition picks, with what its account says.

        The address of the account and the moment it was verified are read in
        the same statement, because a confirmation is sent to the first and
        allowed by the second (BR-47). The join is an outer one, because a
        walk-in has a profile and no account.
        """
        statement = (
            select(CustomerProfile, col(UserAccount.email), col(UserAccount.email_verified_at))
            .outerjoin(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
            .where(condition)
        )
        found = self._session.exec(statement).first()
        logger.debug(
            "identity.customer_profile_lookup_finished",
            extra={**sought, "found": found is not None},
        )
        if found is None:
            return None
        row, email, email_verified_at = found
        return domain.CustomerProfile(
            id=row.id,
            user_account_id=row.user_account_id,
            display_name=row.display_name,
            account_status=row.account_status,
            email=email,
            trade_discount_percent=Decimal(row.trade_discount_percent),
            email_verified=email_verified_at is not None,
        )


class SqlBranchDirectory:
    """Lists the trading branches through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the directory to the session of the request."""
        self._session = session

    def list_active(self) -> list[BranchListing]:
        """Return every active branch, ordered by name and then by code.

        The code breaks a tie between two branches of the same name, so the
        order is the same on every call. An availability search lists its
        branches in this order too.
        """
        statement = (
            select(Branch)
            .where(col(Branch.is_active))
            .order_by(col(Branch.name), col(Branch.code))
        )
        with logged_query(logger, "identity.branch_directory", {"active_only": True}) as outcome:
            rows = self._session.exec(statement).all()
            outcome.row_count = len(rows)
        return [
            BranchListing(
                code=row.code,
                name=row.name,
                suburb=row.suburb,
                city=row.city,
                phone=row.phone,
                opens_at=row.opens_at,
                closes_at=row.closes_at,
            )
            for row in rows
        ]
