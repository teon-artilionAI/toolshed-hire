"""The monthly job that anonymises customers nobody has heard from in two years (#113).

    python -m app.jobs.anonymise_customers --report
    python -m app.jobs.anonymise_customers

Run it with `--report` first. It then reads every customer who qualifies and
logs how many there are and their keys, a page at a time, and changes nothing.
Without it, each page of up to a hundred customers is anonymised in one
transaction, and the counts of each page and of the run are logged.

The cutoff is two years before the job starts, the same for every page. Pages
follow one another in the order of the customer's key, so a run stopped part
way is finished by the next one, which starts again from the first key.

It connects with DATABASE_URL as the application role, like the API, because
anonymising writes and records an audit event and deletes nothing. ENVIRONMENT
is left unset where it runs, the way the migration and the seed leave it, so
the settings do not ask for the signing key a job never uses.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.clock import Clock
from app.application.identity.anonymise_dormant import (
    DORMANT_BATCH_SIZE,
    AnonymiseDormantCustomersUseCase,
    DormantBatchCommand,
)
from app.application.unit_of_work import UnitOfWork
from app.domain.anonymisation import dormancy_cutoff
from app.jobs.job_run import JobFacts, run_job
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

JOB_NAME: Final[str] = "anonymise-customers"
REPORT_FLAG: Final[str] = "--report"
BATCH_SIZE_FLAG: Final[str] = "--batch-size"


@dataclass(frozen=True, slots=True)
class AnonymisationTotals:
    """What one run found and did, over every page.

    Attributes:
        report_only: True when nothing was written.
        pages: How many pages were read.
        found: How many customers qualified when their page was read.
        anonymised: How many were anonymised.
        skipped: How many no longer qualified once read again under a lock.

    """

    report_only: bool
    pages: int
    found: int
    anonymised: int
    skipped: int

    def facts(self) -> JobFacts:
        """Return the totals as the job's last log line reports them."""
        return {
            "report_only": self.report_only,
            "pages": self.pages,
            "found_count": self.found,
            "anonymised_count": self.anonymised,
            "skipped_count": self.skipped,
        }


def anonymise_dormant_customers(
    open_unit_of_work: Callable[[], UnitOfWork],
    clock: Clock,
    *,
    report_only: bool,
    batch_size: int = DORMANT_BATCH_SIZE,
) -> AnonymisationTotals:
    """Read, and unless only reporting anonymise, every dormant customer a page at a time.

    Args:
        open_unit_of_work: Returns a fresh unit of work for each page.
        clock: Where the run's instant comes from.
        report_only: True to write nothing.
        batch_size: The most customers in one page and one transaction.

    """
    cutoff = dormancy_cutoff(clock.now())
    after: UUID | None = None
    pages = found = anonymised = skipped = 0
    while True:
        use_case = AnonymiseDormantCustomersUseCase(open_unit_of_work(), clock)
        batch = use_case.execute(
            DormantBatchCommand(
                cutoff=cutoff, after=after, batch_size=batch_size, report_only=report_only
            )
        )
        pages += 1
        found += len(batch.found)
        anonymised += len(batch.anonymised)
        skipped += len(batch.skipped)
        if len(batch.found) < batch_size:
            break
        after = batch.last_key
    return AnonymisationTotals(
        report_only=report_only,
        pages=pages,
        found=found,
        anonymised=anonymised,
        skipped=skipped,
    )


def parse_arguments(arguments: Sequence[str]) -> argparse.Namespace:
    """Read `--report` and `--batch-size` from the command line."""
    parser = argparse.ArgumentParser(
        prog="python -m app.jobs.anonymise_customers",
        description="Anonymise customers whose last hire ended more than two years ago.",
    )
    parser.add_argument(
        REPORT_FLAG,
        action="store_true",
        help="List how many customers would be anonymised, and which, and change nothing.",
    )
    parser.add_argument(
        BATCH_SIZE_FLAG,
        type=int,
        default=DORMANT_BATCH_SIZE,
        help=f"How many customers one transaction anonymises. {DORMANT_BATCH_SIZE} by default.",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the job against the database DATABASE_URL names, and return the exit status."""
    options = parse_arguments(sys.argv[1:] if arguments is None else arguments)

    def work() -> JobFacts:
        # Imported here, because importing the database module builds the
        # engine from the settings, and parsing the arguments needs neither.
        from sqlmodel import Session

        from app.config import settings
        from app.infrastructure.clock import clock_for
        from app.infrastructure.database import engine
        from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

        totals = anonymise_dormant_customers(
            lambda: SqlAlchemyUnitOfWork(lambda: Session(engine)),
            clock_for(settings.test_business_time),
            report_only=options.report,
            batch_size=options.batch_size,
        )
        return totals.facts()

    configure_logging()
    return run_job(JOB_NAME, work)


if __name__ == "__main__":
    sys.exit(main())
