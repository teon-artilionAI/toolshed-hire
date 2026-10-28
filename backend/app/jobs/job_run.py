"""How a maintenance job starts, reports and ends, which every job shares.

A job writes the same JSON log lines the API does, so Cloud Logging reads them
the same way. It logs its start and its end with how long it took, and a
failure is logged with its traceback and ends the process with a non zero
status, which is what makes Cloud Run mark the execution as failed and retry
it. Nothing is printed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Final

logger = logging.getLogger(__name__)

EXIT_SUCCESS: Final[int] = 0
EXIT_FAILURE: Final[int] = 1
MILLISECONDS_PER_SECOND: Final[int] = 1000

type JobFacts = Mapping[str, str | int | bool | None]


def run_job(name: str, work: Callable[[], JobFacts]) -> int:
    """Run one job and return the process exit status.

    The caller configures logging first, once, as the entry point of the
    process.

    Args:
        name: The job's name, which every line it logs about itself carries.
        work: The job. It returns the counts its last line reports.

    Returns:
        Zero when the job finished, one when it raised.

    """
    started = perf_counter()
    logger.info("job.started", extra={"job": name})
    try:
        facts = work()
    except Exception as exc:  # noqa: BLE001  the entry point reports and exits
        logger.exception(
            "job.failed",
            extra={
                "job": name,
                "error_type": type(exc).__name__,
                "duration_ms": _elapsed_ms(started),
            },
        )
        return EXIT_FAILURE
    logger.info(
        "job.finished", extra={"job": name, "duration_ms": _elapsed_ms(started), **facts}
    )
    return EXIT_SUCCESS


def _elapsed_ms(started: float) -> int:
    """Return the milliseconds since `started`, from the performance counter."""
    return round((perf_counter() - started) * MILLISECONDS_PER_SECOND)
