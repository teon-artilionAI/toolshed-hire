"""The monthly anonymisation of customers nobody has heard from in two years (#113).

The privacy notice says personal details are removed two years after the last
hire unless the account is still in use. Once a month the job asks for the
next page of customers who qualify, in the order of their key, and anonymises
that page in one transaction, the same way the owner's request does. Each page
is a batch of its own, so a failure loses at most one batch, and the job
carries on from the last key of the page before.

A customer is read again under a lock before anything is written. One who
signed in, booked or ran up a balance since the page was read is skipped with
a warning naming why, and the rest of the batch goes ahead. The event of each
one names the schedule as the trigger and has no actor and no reason.

In report mode the page is read and nothing is written, so the job can be run
first to see how many customers it would anonymise and which.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.identity.anonymise_customer import anonymise_in
from app.application.use_case import UseCase
from app.domain.anonymisation import AnonymisationTrigger
from app.domain.errors import NotFound, StateTransitionError

logger = logging.getLogger(__name__)

# How many customers one transaction anonymises.
DORMANT_BATCH_SIZE: Final[int] = 100


@dataclass(frozen=True, slots=True)
class DormantBatchCommand:
    """One page of the monthly job.

    Attributes:
        cutoff: Two years before the run, the same for every page.
        after: The last key of the page before, or None for the first.
        batch_size: The most customers in the page.
        report_only: True to read the page and write nothing.

    """

    cutoff: datetime
    after: UUID | None
    batch_size: int = DORMANT_BATCH_SIZE
    report_only: bool = False


@dataclass(frozen=True, slots=True)
class DormantBatch:
    """What one page found and did.

    Attributes:
        found: The customers that qualified when the page was read, in key order.
        anonymised: Those anonymised. Empty in report mode.
        skipped: Those read again under the lock and found no longer to qualify.

    """

    found: tuple[UUID, ...]
    anonymised: tuple[UUID, ...] = field(default_factory=tuple)
    skipped: tuple[UUID, ...] = field(default_factory=tuple)

    @property
    def last_key(self) -> UUID | None:
        """Return the key the next page starts after, or None when the page was empty."""
        return self.found[-1] if self.found else None


class AnonymiseDormantCustomersUseCase(UseCase[DormantBatchCommand, DormantBatch]):
    """Anonymise one page of dormant customers in one transaction, or only report it."""

    def execute(self, command: DormantBatchCommand) -> DormantBatch:
        """Read the next page and anonymise it, unless the command only asks for a report.

        Raises:
            ValueError: If the batch size is below one.

        """
        if command.batch_size < 1:
            raise ValueError(
                f"Attempted to anonymise dormant customers in batches of {command.batch_size}. "
                "A batch is at least one customer."
            )
        logger.info(
            "anonymisation.batch_started",
            extra={
                "cutoff": command.cutoff.isoformat(),
                "after": str(command.after) if command.after is not None else None,
                "batch_size": command.batch_size,
                "report_only": command.report_only,
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            found = uow.personal_data.dormant_customers(
                command.cutoff, after=command.after, limit=command.batch_size
            )
            if command.report_only:
                batch = DormantBatch(found=found)
                self._log_finished(batch, command)
                return batch
            anonymised: list[UUID] = []
            skipped: list[UUID] = []
            for customer_profile_id in found:
                try:
                    anonymise_in(
                        uow,
                        customer_profile_id=customer_profile_id,
                        trigger=AnonymisationTrigger.SCHEDULE,
                        actor=None,
                        reason=None,
                        now=now,
                        dormant_since=command.cutoff,
                    )
                except (NotFound, StateTransitionError) as refusal:
                    self._log_skipped(customer_profile_id, refusal.message)
                    skipped.append(customer_profile_id)
                    continue
                anonymised.append(customer_profile_id)
            uow.commit()
        batch = DormantBatch(found=found, anonymised=tuple(anonymised), skipped=tuple(skipped))
        self._log_finished(batch, command)
        return batch

    @staticmethod
    def _log_skipped(customer_profile_id: UUID, why: str) -> None:
        """Say that a customer on the page no longer qualified, and why."""
        logger.warning(
            "anonymisation.customer_skipped",
            extra={"customer_profile_id": str(customer_profile_id), "why": why},
        )

    @staticmethod
    def _log_finished(batch: DormantBatch, command: DormantBatchCommand) -> None:
        """Write the counts of one page, and its keys, which say no more than which rows."""
        logger.info(
            "anonymisation.batch_finished",
            extra={
                "report_only": command.report_only,
                "found_count": len(batch.found),
                "anonymised_count": len(batch.anonymised),
                "skipped_count": len(batch.skipped),
                "customer_profile_ids": [str(key) for key in batch.found],
                "last_key": str(batch.last_key) if batch.last_key is not None else None,
            },
        )
