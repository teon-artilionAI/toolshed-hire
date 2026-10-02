"""The SQL side of the identity module, for branches and customer profiles.

The two repositories are read only here. They map the SQLModel table classes to
the small domain entities a booking needs, and they run on the session of the
unit of work that created them.

`SqlBranchDirectory` is the read side. It lists the trading branches for a
visitor and returns read models, never a table row.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session, col, select

from app.application.identity.read_models import BranchListing
from app.domain import identity as domain
from app.infrastructure.models import Branch, CustomerProfile, UserAccount
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)


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


class SqlCustomerRepository:
    """Reads customer profiles through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def profile_for_account(self, user_account_id: UUID) -> domain.CustomerProfile | None:
        """Return the customer profile that belongs to a sign in account.

        The address of the account is read in the same statement, because a
        booking confirmation is sent to it.
        """
        logger.debug(
            "identity.customer_profile_lookup_started",
            extra={"customer_user_id": str(user_account_id)},
        )
        statement = (
            select(CustomerProfile, col(UserAccount.email))
            .join(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
            .where(col(CustomerProfile.user_account_id) == user_account_id)
        )
        found = self._session.exec(statement).first()
        logger.debug(
            "identity.customer_profile_lookup_finished",
            extra={"customer_user_id": str(user_account_id), "found": found is not None},
        )
        if found is None:
            return None
        row, email = found
        return domain.CustomerProfile(
            id=row.id,
            user_account_id=row.user_account_id,
            display_name=row.display_name,
            account_status=row.account_status,
            email=email,
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
