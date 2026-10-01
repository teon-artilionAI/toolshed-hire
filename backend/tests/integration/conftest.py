"""Collection order for the integration suite.

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
"""

from __future__ import annotations

import logging
from typing import Final

import pytest

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
