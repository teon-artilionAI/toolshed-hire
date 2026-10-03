"""The SQL branch repository, which reads branches as the small domain entity.

It runs on the session of whoever made it. A unit of work makes one for the
use cases, and the counter's dashboard and diary make one on the session of the
request, because a read writes nothing and needs no unit of work.

The read side that lists the trading branches for a visitor is
`SqlBranchDirectory`.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session, col, select

from app.domain import identity as domain
from app.infrastructure.models import Branch

logger = logging.getLogger(__name__)


class SqlBranchRepository:
    """Reads branches through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session it reads through."""
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
