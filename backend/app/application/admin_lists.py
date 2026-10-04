"""The paging every list of the admin console shares.

Every list the administrator reads is `{"items": [...], "page": 1,
"pageSize": 20, "total": 0}`, with `page` from one and `pageSize` from one to a
hundred. The audit log and the notification log page by these. The API holds a
request to them, and a query object turns a page into an offset.
"""

from __future__ import annotations

from typing import Final

from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE

MINIMUM_PAGE_SIZE: Final[int] = 1
MAXIMUM_PAGE_SIZE: Final[int] = 100
DEFAULT_PAGE_SIZE: Final[int] = 20


def offset_of(page: int, page_size: int) -> int:
    """Return how many rows come before the first one on a page."""
    return (page - FIRST_PAGE) * page_size


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "FIRST_PAGE",
    "MAXIMUM_PAGE",
    "MAXIMUM_PAGE_SIZE",
    "MINIMUM_PAGE_SIZE",
    "offset_of",
]
