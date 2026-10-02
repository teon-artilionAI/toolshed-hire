"""The SQL repositories of the identity module, for branches and customer profiles.

Both are read only here. They map the SQLModel table classes to the small
domain entities a booking needs, and they run on the session of the unit of
work that created them.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session, col, select

from app.domain import identity as domain
from app.infrastructure.models import Branch, CustomerProfile, UserAccount

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
