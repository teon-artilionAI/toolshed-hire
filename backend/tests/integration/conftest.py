"""Collection order for the integration suite, and the seeded database fixtures.

The schema baseline test has to run before every other test. It asserts that
the extensions, the tables, the exclusion constraint and the partial indexes
exist, and every other integration test assumes all of that. If it ran last, a
broken migration would show up as a page of unrelated failures with the one
that explains them at the bottom.

pytest collects the files of a directory in name order, which would put
test_schema_baseline.py after the other two. The order is set here by a
collection hook, which needs no plugin and leaves the file with the name that
says what it holds. A numeric prefix on the file name would do the same job
only until somebody added a file that sorted ahead of it.

`seeded` and `reader` serve the seed tests. The database is emptied and seeded
once for each module that asks, because loading four hundred units for every
assertion would only make the suite slower.

`booking` at the foot of the file serves the reservation tests. It drives the
six reservation routes of the real application on the real database, on a
clock that stands still.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from seeding import SeedTally, seed_database
from tests.support.booking_api import BookingClient
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD
from tests.support.pg import truncate_schema_tables
from tests.support.sessions import session_client

logger = logging.getLogger(__name__)

SCHEMA_BASELINE_MODULE: Final[str] = "test_schema_baseline.py"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Move the schema baseline tests to the front of the run.

    The sort is stable and its key is only whether a test belongs to the
    baseline module, so the baseline tests keep their own order and every other
    test keeps the order pytest collected it in.

    Args:
        items: Every collected test, reordered in place.

    """
    items.sort(key=lambda item: item.path.name != SCHEMA_BASELINE_MODULE)
    moved = sum(item.path.name == SCHEMA_BASELINE_MODULE for item in items)
    logger.debug("test.schema_baseline_ordered_first", extra={"baseline_test_count": moved})


@pytest.fixture(scope="module")
def seeded(postgres_engine: Engine) -> Iterator[SeedTally]:
    """Empty the database, seed it once and yield what that first run reported.

    Module scoped, so the tables are emptied again when the module finishes and
    the next module starts from nothing, as every other integration test does.
    """
    truncate_schema_tables(postgres_engine)
    with Session(postgres_engine) as session:
        tally = seed_database(session, TEST_PASSWORD)
        session.commit()
    logger.info(
        "test.database_seeded",
        extra={"created_count": tally.total_created, "found_count": tally.total_found},
    )
    try:
        yield tally
    finally:
        truncate_schema_tables(postgres_engine)


@pytest.fixture
def reader(postgres_engine: Engine, seeded: SeedTally) -> Iterator[Session]:
    """Yield a fresh session on the seeded database."""
    with Session(postgres_engine) as session:
        yield session


@pytest.fixture
def still_clock() -> FixedClock:
    """Return a clock that stands still until the test moves it."""
    return FixedClock()


@pytest.fixture
def booking(postgres_session: Session, still_clock: FixedClock) -> Iterator[BookingClient]:
    """Yield the reservation routes on the real database and the still clock."""
    with session_client(postgres_session, still_clock) as client:
        yield BookingClient(client, still_clock)
