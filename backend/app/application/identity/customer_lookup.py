"""The counter looking a customer up, which is US-21.

Staff search by part of a name, by a phone number or by the email address of
an account, and open one customer by the key the search returned. Nothing is
written, so nothing is audited and nothing is committed. The reads go through
the customer directory of the unit of work.

The text a member of staff searched for is never written to the log, only its
length, because a search box is where people type names, numbers and
addresses that a log should not keep.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from app.application.identity.customer_directory import (
    CustomerPage,
    CustomerSearch,
    CustomerSummary,
)
from app.application.unit_of_work import UnitOfWork
from app.domain.errors import NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

CUSTOMER_NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find that customer. Search for them again."
)


def read_customer(uow: UnitOfWork, customer_profile_id: UUID) -> CustomerSummary:
    """Return one customer as the counter sees one, inside an open unit of work.

    Raises:
        NotFound: If there is no customer profile with this key.

    """
    summary = uow.customer_directory.summary(customer_profile_id)
    if summary is None:
        logger.info(
            "customer.not_found", extra={"customer_profile_id": str(customer_profile_id)}
        )
        raise NotFound(
            CUSTOMER_NOT_FOUND_MESSAGE, {"customer_profile_id": str(customer_profile_id)}
        )
    return summary


class LookUpCustomers:
    """Find customers for a member of staff at the counter."""

    def __init__(self, uow: UnitOfWork) -> None:
        """Keep the unit of work the reads run in."""
        self._uow = uow

    def search(self, actor: Actor, search: CustomerSearch) -> CustomerPage:
        """Return one page of the customers the text matches, best match first."""
        logger.info(
            "customer.search_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "text_length": len(search.text),
                "page": search.page,
                "page_size": search.page_size,
            },
        )
        with self._uow as uow:
            found = uow.customer_directory.search(search)
        logger.info(
            "customer.search_finished",
            extra={"returned": len(found.items), "total": found.total, "page": found.page},
        )
        return found

    def one(self, actor: Actor, customer_profile_id: UUID) -> CustomerSummary:
        """Return one customer.

        Raises:
            NotFound: If there is no customer profile with this key.

        """
        logger.info(
            "customer.read_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "customer_profile_id": str(customer_profile_id),
            },
        )
        with self._uow as uow:
            summary = read_customer(uow, customer_profile_id)
        logger.info(
            "customer.read_finished", extra={"customer_profile_id": str(customer_profile_id)}
        )
        return summary
