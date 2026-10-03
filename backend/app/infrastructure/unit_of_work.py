"""The SQLAlchemy unit of work, one session shared by every repository.

`SqlAlchemyUnitOfWork` implements the unit of work port. Entering it obtains a
session and builds the repositories, the audit log and the outbox over that one
session, so everything written through them belongs to one transaction. Commit
is explicit. Leaving the block always rolls back whatever was not committed.

The session comes from a factory, which is how the two ways of running differ.
A request hands in the request scoped session, so the use case and the
authentication dependency see the same transaction, and the session is left
open for the request to close. A script or a test that wants a transaction of
its own hands in a factory that opens a session, and the unit of work closes it
on the way out.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlmodel import Session

from app.application.audit import AuditLog
from app.application.availability.ports import AssetRepository
from app.application.booking.ports import ReservationRepository
from app.application.catalogue.ports import ProductModelRepository
from app.application.hire.ports import RentalRepository
from app.application.identity.customer_directory import CustomerDirectory
from app.application.identity.ports import (
    AccountRepository,
    BranchRepository,
    CustomerRepository,
    SessionRepository,
)
from app.application.notification.ports import NotificationOutbox
from app.application.throttle import RateLimitStore
from app.infrastructure.audit import SqlAuditLog
from app.infrastructure.availability import SqlAssetRepository
from app.infrastructure.booking import SqlReservationRepository
from app.infrastructure.catalogue import SqlProductModelRepository
from app.infrastructure.customer_search import SqlCustomerDirectory
from app.infrastructure.identity import SqlBranchRepository, SqlCustomerRepository
from app.infrastructure.identity_accounts import SqlAccountRepository
from app.infrastructure.identity_sessions import SqlSessionRepository
from app.infrastructure.notification.outbox import SqlNotificationOutbox
from app.infrastructure.rate_limit import SqlRateLimitStore
from app.infrastructure.rentals import SqlRentalRepository

logger = logging.getLogger(__name__)


class SqlAlchemyUnitOfWork:
    """One transaction over one session, and the repositories that write in it."""

    reservations: ReservationRepository
    assets: AssetRepository
    rentals: RentalRepository
    branches: BranchRepository
    product_models: ProductModelRepository
    customers: CustomerRepository
    customer_directory: CustomerDirectory
    accounts: AccountRepository
    sessions: SessionRepository
    rate_limits: RateLimitStore
    notifications: NotificationOutbox
    audit: AuditLog

    def __init__(
        self, session_factory: Callable[[], Session], *, close_on_exit: bool = True
    ) -> None:
        """Create the unit of work. No session is obtained until it is entered.

        Args:
            session_factory: Returns the session to work in.
            close_on_exit: True when the factory opens a session this unit of
                work owns and must close. False when the session belongs to
                somebody else, such as the request, who will close it.

        """
        self._session_factory = session_factory
        self._close_on_exit = close_on_exit
        self._session: Session | None = None

    def __enter__(self) -> Self:
        """Obtain the session and build the repositories over it.

        Raises:
            RuntimeError: If the unit of work is already open. One instance
                holds one transaction at a time.

        """
        if self._session is not None:
            raise RuntimeError(
                "Attempted to enter a unit of work that is already open. Leave the first "
                "`with` block before entering it again."
            )
        session = self._session_factory()
        self._session = session
        self.reservations = SqlReservationRepository(session)
        self.assets = SqlAssetRepository(session)
        self.rentals = SqlRentalRepository(session)
        self.branches = SqlBranchRepository(session)
        self.product_models = SqlProductModelRepository(session)
        self.customers = SqlCustomerRepository(session)
        self.customer_directory = SqlCustomerDirectory(session)
        self.accounts = SqlAccountRepository(session)
        self.sessions = SqlSessionRepository(session)
        self.rate_limits = SqlRateLimitStore(session)
        self.notifications = SqlNotificationOutbox(session)
        self.audit = SqlAuditLog(session)
        logger.debug("unit_of_work.opened", extra={"owns_session": self._close_on_exit})
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back whatever was not committed, and close a session this object owns.

        After a commit the rollback finds nothing to undo. After an exception
        it discards everything the block wrote, which is what keeps a booking
        whose audit event could not be written from existing at all.
        """
        session = self._open_session()
        try:
            session.rollback()
        finally:
            if self._close_on_exit:
                session.close()
            self._session = None
        if exc_type is None:
            logger.debug("unit_of_work.closed")
        else:
            logger.info("unit_of_work.rolled_back", extra={"cause": exc_type.__name__})

    def commit(self) -> None:
        """Make everything written so far permanent."""
        self._open_session().commit()
        logger.debug("unit_of_work.committed")

    def rollback(self) -> None:
        """Discard everything written since the last commit."""
        self._open_session().rollback()
        logger.debug("unit_of_work.rollback_requested")

    def _open_session(self) -> Session:
        """Return the session of the open unit of work.

        Raises:
            RuntimeError: If the unit of work is used outside its `with` block.

        """
        if self._session is None:
            raise RuntimeError(
                "Attempted to use a unit of work outside its `with` block. Enter it first, "
                "so there is a transaction to commit or roll back."
            )
        return self._session
