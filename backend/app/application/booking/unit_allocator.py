"""The allocator a reservation takes its units through, shared by the hold and the reallocation.

A reservation state asks for units through a `UnitAllocator` (BR-07). This is
the one that runs, and it takes them through the existing allocation
algorithm, `allocate_assets`, so the locking query, the exclusion constraint
and the translation of a conflict are the ones a hold has always used. A hold
asks for every unit of a line, and a reallocation asks for the units a line is
short of after one was released by hand (US-32). Both are a line's shortfall,
because a draft line holds nothing.

The conflict a customer is shown names the model and the dates. It never says
how many units are left (US-07). The counts go to the log.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final
from uuid import UUID

from app.application.availability.allocation import AllocationCommand, allocate_assets
from app.application.availability.ports import AssetRepository
from app.application.clock import Clock
from app.application.unit_of_work import UnitOfWork
from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation, ReservationLine
from app.domain.catalogue import ProductModel
from app.domain.errors import AllocationConflictError

logger = logging.getLogger(__name__)

# What a conflict calls the branch when its name cannot be read.
UNNAMED_BRANCH: Final[str] = "this branch"
# The log lines a refusal is written under, for a hold and for a reallocation.
HOLD_REFUSED_EVENT: Final[str] = "reservation.hold_refused"
REALLOCATION_REFUSED_EVENT: Final[str] = "reservation.reallocation_refused"


def date_in_words(day: date) -> str:
    """Return a date as a customer reads it, for example 9 March 2026."""
    return f"{day.day} {day:%B} {day.year}"


class RepositoryAllocator:
    """Takes the units a line is short of through the allocation algorithm.

    It keeps the tags of what it held, for the audit event.
    """

    def __init__(
        self,
        assets: AssetRepository,
        clock: Clock,
        models: Mapping[UUID, ProductModel],
        branch_name: str,
        refusal_event: str = HOLD_REFUSED_EVENT,
    ) -> None:
        """Bind the allocator to the asset repository of the open unit of work.

        Args:
            assets: The asset repository of the open unit of work.
            clock: Where the moment of each hold comes from.
            models: The product model of every line, by its key.
            branch_name: The name of the collection branch, for a refusal.
            refusal_event: The name of the log line a refusal is written under.

        """
        self._assets = assets
        self._clock = clock
        self._models = models
        self._branch_name = branch_name
        self._refusal_event = refusal_event
        self.asset_tags: list[str] = []

    def allocate(
        self, reservation: Reservation, line: ReservationLine
    ) -> Sequence[AssetAllocation]:
        """Hold the units a line is short of, or refuse in words a customer can act on.

        Raises:
            AllocationConflictError: If too few units are free, or the
                exclusion constraint refused one. The sentence names the model
                and the dates and carries no count.

        """
        model = self._models[line.product_model_id]
        period = reservation.period
        wanted = line.shortfall()
        try:
            held = allocate_assets(
                self._assets,
                self._clock,
                AllocationCommand(
                    reservation_line_id=line.id,
                    product_model_id=line.product_model_id,
                    branch_id=reservation.branch_id,
                    period=period,
                    quantity=wanted,
                ),
            )
        except AllocationConflictError as conflict:
            logger.warning(
                self._refusal_event,
                extra={
                    "reference": reservation.reference,
                    "sku": model.sku,
                    "period": period.as_postgres_daterange(),
                    "requested_quantity": wanted,
                    "available_quantity": conflict.detail.get("available_quantity"),
                    "constraint": conflict.detail.get("constraint_name"),
                    "outcome": "nothing was allocated",
                },
            )
            raise AllocationConflictError(
                f"{model.name} is not available at {self._branch_name} from "
                f"{date_in_words(period.start)} to {date_in_words(period.end)}. "
                "Choose other dates or another branch.",
                model_slug=model.slug,
                period=period.as_postgres_daterange(),
            ) from conflict
        self.asset_tags.extend(item.asset_tag for item in held)
        return [item.allocation for item in held]


def allocator_for(
    uow: UnitOfWork,
    clock: Clock,
    reservation: Reservation,
    models: Mapping[UUID, ProductModel],
    refusal_event: str = HOLD_REFUSED_EVENT,
) -> RepositoryAllocator:
    """Return the allocator of a reservation, over the asset repository of the open unit of work.

    Args:
        uow: The open unit of work.
        clock: Where the moment of each hold comes from.
        reservation: The reservation the units are for.
        models: The product model of every line, from `line_models_of`.
        refusal_event: The name of the log line a refusal is written under.

    """
    return RepositoryAllocator(
        uow.assets, clock, models, branch_name_of(uow, reservation), refusal_event
    )


def line_models_of(uow: UnitOfWork, reservation: Reservation) -> dict[UUID, ProductModel]:
    """Return the product model of every line, by its key.

    Raises:
        LookupError: If a model cannot be read. A line carries a foreign key
            to its model and nothing is ever deleted, so this is a fault in
            the data and not something a caller can put right.

    """
    models: dict[UUID, ProductModel] = {}
    for line in reservation.lines:
        model = uow.product_models.get(line.product_model_id)
        if model is None:
            raise LookupError(
                f"Attempted to allocate units to reservation {reservation.reference}, and "
                f"product model {line.product_model_id} of line {line.line_position} could "
                "not be read."
            )
        models[model.id] = model
    return models


def branch_name_of(uow: UnitOfWork, reservation: Reservation) -> str:
    """Return the name of the collection branch, for the sentence of a conflict."""
    branch = uow.branches.get(reservation.branch_id)
    return branch.name if branch is not None else UNNAMED_BRANCH
