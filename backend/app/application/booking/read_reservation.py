"""Reading one reservation, and a list of them, on behalf of somebody (FR-09, BR-42).

A customer reads their own reservations and nobody else's. One who asks for a
reservation that is not theirs is told there is no such reservation, in the
words used for a reference nobody ever issued. The scope of the reader goes
into the query, so a read never holds a record it then has to decide not to
return. Staff read any customer's reservation, at any branch.

A read can be the first thing to happen after a hold has run out, so the sweep
runs before either read (BR-13). The batch is bounded, so a single read also
makes sure of the one reservation it is about to show. A hold that is overdue
is lapsed before it is shown, and the reader is never told that a reservation
is on hold when its units are about to be given to somebody else.

Only staff may narrow a list to one customer or one branch. A customer's list
is already their own.

A customer's list leaves out the baskets they abandoned. A reservation that
was cancelled without ever holding a unit is a draft that was replaced by a
changed basket or thrown away, and not a cancelled booking. The query leaves
it out, so a page is never short of what it says it holds. Staff still see
every reservation, and anybody may still read an abandoned one by its key.

What degrades first as the data grows is the list. A page is found with
OFFSET, so a deep page reads and throws away every row before it, and the
total is a count of every row that matches. A customer's list is short and
indexed by customer. The list staff ask for with no filter sorts the whole
table by the time of creation, which has no index. That is the first thing to
slow down, and the fix is a page keyed on the creation time with an index
behind it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.availability.search import BRANCH_PARAMETER, UNKNOWN_BRANCH_MESSAGE
from app.application.booking.access import ReservationCommand, is_staff, read_detail
from app.application.booking.expire_holds import (
    ExpireHoldsAndNoShowsUseCase,
    SweepCommand,
    settle_overdue_hold,
)
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    ReservationKey,
    ReservationSearch,
)
from app.application.booking.views import (
    ReservationView,
    ReservationViewPage,
    page_for,
    view_for,
)
from app.application.catalogue.read_models import FIRST_PAGE
from app.application.clock import Clock
from app.application.ownership import owner_scope_for
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import ReservationStatus
from app.domain.errors import AuthorisationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

STAFF_ONLY_FILTER_MESSAGE: Final[str] = (
    "Only a member of staff can list the reservations of another customer or of one branch."
)


@dataclass(frozen=True, slots=True)
class ListReservationsQuery:
    """Which reservations a caller wants listed.

    Attributes:
        actor: Who is asking, with the role and the branch they hold.
        status: Only reservations in this status, or None for every status.
        customer_profile_id: Only this customer's. Staff only.
        branch_code: Only those collected at this branch. Staff only.
        page: The page wanted, counted from one.
        page_size: How many reservations a page holds.
        branch_parameter: The name the branch code was sent under, which a
            refusal of it names.

    """

    actor: Actor
    status: ReservationStatus | None = None
    customer_profile_id: UUID | None = None
    branch_code: str | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    branch_parameter: str = BRANCH_PARAMETER


class ReadReservations:
    """Return reservations to a reader who is allowed to see them."""

    def __init__(
        self, uow: UnitOfWork, clock: Clock, sweep: ExpireHoldsAndNoShowsUseCase
    ) -> None:
        """Keep the unit of work the reads run in, the clock and the sweep."""
        self._uow = uow
        self._clock = clock
        self._sweep = sweep

    def one(self, command: ReservationCommand) -> ReservationView:
        """Return one reservation, or refuse as though it did not exist.

        Raises:
            NotFound: If there is no such reservation, or if the actor is a
                customer and it belongs to somebody else. The two are not
                distinguished.

        """
        actor, key = command.actor, command.key
        logger.info(
            "reservation.read_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(key),
            },
        )
        self._sweep.execute(SweepCommand())
        now = self._clock.now()
        with self._uow as uow:
            detail = read_detail(uow, actor, key)
            if detail.hold_is_overdue(now):
                self._lapse(uow, actor, ReservationKey.of(detail.id))
                detail = read_detail(uow, actor, key)
        logger.info(
            "reservation.read_finished",
            extra={"reference": detail.reference, "outcome": detail.status.value},
        )
        return view_for(actor, detail, now)

    def page(self, query: ListReservationsQuery) -> ReservationViewPage:
        """Return one page of the reservations the caller may see, newest first.

        Raises:
            AuthorisationFailure: If a customer asks for another customer's
                reservations or for those of one branch.
            ValidationFailure: Naming `branch` when the code is not the code
                of a trading branch.

        """
        actor = query.actor
        if not is_staff(actor) and (query.customer_profile_id or query.branch_code):
            raise AuthorisationFailure(
                STAFF_ONLY_FILTER_MESSAGE, {"required_roles": ["ADMIN", "COUNTER_STAFF"]}
            )
        self._sweep.execute(SweepCommand())
        now = self._clock.now()
        with self._uow as uow:
            search = ReservationSearch(
                status=query.status,
                customer_profile_id=query.customer_profile_id,
                branch_id=_branch_id_of(uow, query.branch_code, query.branch_parameter),
                page=query.page,
                page_size=query.page_size,
            )
            found = uow.reservations.search(search, owner_scope_for(actor))
        logger.info(
            "reservation.list_finished",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "status": query.status.value if query.status else None,
                "page": found.page,
                "page_size": found.page_size,
                "total": found.total,
            },
        )
        return page_for(actor, found, now)

    def _lapse(self, uow: UnitOfWork, actor: Actor, key: ReservationKey) -> None:
        """Lapse the one overdue hold a read is about to show, and commit that."""
        reservation = uow.reservations.find_for_update(key, owner_scope_for(actor))
        if reservation is not None:
            settle_overdue_hold(uow, reservation, self._clock.now())


def _branch_id_of(uow: UnitOfWork, branch_code: str | None, parameter: str) -> UUID | None:
    """Return the key of the trading branch a list is narrowed to, or None.

    Raises:
        ValidationFailure: Naming the parameter the code was sent under when
            no trading branch has the code.

    """
    if branch_code is None:
        return None
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        raise refused(parameter, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    return branch.id
