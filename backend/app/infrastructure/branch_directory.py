"""The read side of the branches, which lists the trading branches for a visitor.

`SqlBranchDirectory` implements the `BranchDirectory` port. It returns read
models, never a table row, and runs on the session of the request, because a
read writes nothing and needs no unit of work.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, col, select

from app.application.identity.read_models import BranchListing
from app.infrastructure.models import Branch
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)


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
