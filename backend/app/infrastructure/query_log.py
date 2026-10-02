"""The two log lines every read side query writes.

A query logs when it starts and when it finishes. The line at the end carries
the filters it ran with, how many rows came back and how long it took, so a
slow search shows up in the log with everything needed to run it again.

The filters are whatever the query passes in. A query never passes the free
text a visitor typed, only its length, because a search box is where people
paste things they should not.

A query that raises writes no finishing line. The error handler logs the fault
with the same request id, and a finishing line would only say the same thing
twice.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Final

MILLISECONDS_PER_SECOND: Final[int] = 1000
DURATION_DECIMALS: Final[int] = 2
STARTED_SUFFIX: Final[str] = "_started"
FINISHED_SUFFIX: Final[str] = "_finished"


@dataclass
class QueryOutcome:
    """What a query reports about itself once it has run.

    Attributes:
        row_count: How many rows the query returned.

    """

    row_count: int = 0


@contextmanager
def logged_query(
    log: logging.Logger, event: str, filters: Mapping[str, object]
) -> Iterator[QueryOutcome]:
    """Log the start and the end of one query.

    Args:
        log: The logger of the module that runs the query.
        event: The event name without a suffix, for example
            `catalogue.model_search`.
        filters: What the query was asked with. Never a free text value.

    Yields:
        The outcome, which the query fills in with its row count.

    """
    outcome = QueryOutcome()
    started = perf_counter()
    log.debug(f"{event}{STARTED_SUFFIX}", extra=dict(filters))
    yield outcome
    duration_ms = round((perf_counter() - started) * MILLISECONDS_PER_SECOND, DURATION_DECIMALS)
    log.info(
        f"{event}{FINISHED_SUFFIX}",
        extra={**filters, "row_count": outcome.row_count, "duration_ms": duration_ms},
    )
