"""The two lists of rentals, one for staff and one for the customer (FR-19, US-26, US-29).

Staff list rentals at any branch, because reading is never scoped by branch
(BR-43), and narrow the list by branch, status, customer or to the overdue
hires alone. Overdue hires come first, the most overdue first, and then the
rest, newest first, so the counter's worklist is at the top. A customer lists
their own rentals and nobody else's, newest first, and is never shown an
asset tag (US-07). The scope of the reader goes into the query, so a list
never holds a rental it then has to leave out (BR-42).

The staff list runs the lazy sweep first, which now also moves a hire with a
unit out past its due date to OVERDUE (BR-52), so the status filter and the
order agree with what the sweep would say.

Each list takes a bounded number of statements however long the page is, a
count, the rentals of the page, their items and their charges. What degrades
first as the data grows is the staff list with no filter. It is ordered by
whether a hire is overdue and then by when it went out, which no index holds,
so every rental is sorted to find one page. With a branch, a customer or the
overdue filter the index on the branch and due date or the partial index of
hires still out narrows it first. The durable fix is a page keyed on when the
hire went out, with an index behind it, and the overdue hires as a list of
their own.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.booking.read_models import DEFAULT_PAGE_SIZE
from app.application.catalogue.read_models import FIRST_PAGE
from app.application.clock import Clock
from app.application.hire.list_models import RentalSearch
from app.application.hire.views import RentalViewPage, rental_page_for
from app.application.ownership import owner_scope_for
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import RentalStatus
from app.domain.identity import Actor
from app.domain.policies.late_fee import LateFeePolicy

logger = logging.getLogger(__name__)

# The name the contract gives the branch filter, which a refusal of it names.
BRANCH_CODE_PARAMETER: Final[str] = "branchCode"


@dataclass(frozen=True, slots=True)
class ListRentalsQuery:
    """Which rentals a member of staff wants listed.

    Attributes:
        actor: Who is asking, with the role and the branch they hold.
        branch_code: Only rentals that went out from this branch.
        status: Only rentals in this status.
        overdue_only: Only rentals with a unit out past their due date.
        customer_profile_id: Only this customer's rentals.
        page: The page wanted, counted from one.
        page_size: How many rentals a page holds.

    """

    actor: Actor
    branch_code: str | None = None
    status: RentalStatus | None = None
    overdue_only: bool = False
    customer_profile_id: UUID | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class MyRentalsQuery:
    """Which page of their own rentals a customer wants.

    Attributes:
        actor: The customer.
        page: The page wanted, counted from one.
        page_size: How many rentals a page holds.

    """

    actor: Actor
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE


class ListRentals:
    """Return pages of rentals to a reader who is allowed to see them."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        policy: LateFeePolicy,
        sweep: Callable[[], object],
    ) -> None:
        """Keep the unit of work, the clock, the late fee policy and the sweep.

        Args:
            uow: The unit of work the reads run in.
            clock: Where the current business day comes from.
            policy: The late fee policy, which says what each unit still out
                would owe if it came back today.
            sweep: Runs the lazy sweep, before the staff list is read.

        """
        self._uow = uow
        self._clock = clock
        self._policy = policy
        self._sweep = sweep

    def for_staff(self, query: ListRentalsQuery) -> RentalViewPage:
        """Return one page of rentals at any branch, the overdue first.

        Raises:
            ValidationFailure: Naming `branchCode` when the code is not the
                code of a trading branch.

        """
        actor = query.actor
        logger.info(
            "rental.list_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "branch_code": query.branch_code,
                "status": query.status.value if query.status else None,
                "overdue_only": query.overdue_only,
                "customer_profile_id": (
                    str(query.customer_profile_id) if query.customer_profile_id else None
                ),
            },
        )
        self._sweep()
        today = self._clock.today()
        with self._uow as uow:
            search = RentalSearch(
                today=today,
                branch_id=_branch_id_of(uow, query.branch_code),
                status=query.status,
                overdue_only=query.overdue_only,
                customer_profile_id=query.customer_profile_id,
                overdue_first=True,
                page=query.page,
                page_size=query.page_size,
            )
            found = uow.rentals.search(search, owner_scope_for(actor))
        _log_page("rental.list_finished", actor, found.page, found.page_size, found.total)
        return rental_page_for(actor, found, today, self._policy)

    def for_customer(self, query: MyRentalsQuery) -> RentalViewPage:
        """Return one page of the caller's own rentals, newest first, with no asset tag."""
        actor = query.actor
        logger.info(
            "rental.my_list_requested",
            extra={"actor_user_id": str(actor.user_id), "actor_role": actor.role.value},
        )
        today = self._clock.today()
        with self._uow as uow:
            search = RentalSearch(today=today, page=query.page, page_size=query.page_size)
            found = uow.rentals.search(search, owner_scope_for(actor))
        _log_page("rental.my_list_finished", actor, found.page, found.page_size, found.total)
        return rental_page_for(actor, found, today, self._policy)


def _branch_id_of(uow: UnitOfWork, branch_code: str | None) -> UUID | None:
    """Return the key of the trading branch a list is narrowed to, or None.

    Raises:
        ValidationFailure: Naming `branchCode` when no trading branch has the code.

    """
    if branch_code is None:
        return None
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        raise refused(BRANCH_CODE_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    return branch.id


def _log_page(event: str, actor: Actor, page: int, page_size: int, total: int) -> None:
    """Write the line that says what a list found."""
    logger.info(
        event,
        extra={
            "actor_user_id": str(actor.user_id),
            "actor_role": actor.role.value,
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    )
