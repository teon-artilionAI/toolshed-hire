"""Helpers for reading what the HTTP boundary actually said.

Two things are checked here rather than in every test. A problem document must
arrive as `application/problem+json`, because a correct status code served with
the wrong media type is a contract violation no status assertion would catch.
And the status in the body must match the status on the response, because a
document that disagrees with its own envelope is worse than no document.

The request bodies are built in the frontend's camelCase names, which is what
the React client actually sends.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Final
from uuid import UUID

from httpx import Response

from app.api.errors import PROBLEM_MEDIA_TYPE
from app.domain.period import BookingPeriod

logger = logging.getLogger(__name__)

PROBLEM_TYPE_SEPARATOR: Final[str] = "/"
DEFAULT_DAYS_AHEAD: Final[int] = 7
DEFAULT_HIRE_DAYS: Final[int] = 3
DEFAULT_QUANTITY: Final[int] = 1


def problem_of(response: Response) -> dict[str, object]:
    """Return the parsed problem document, checking the envelope first.

    Args:
        response: An error response from the API.

    Returns:
        The problem document as a dictionary.

    """
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith(PROBLEM_MEDIA_TYPE), (
        f"An error was returned as {content_type!r}. Every error leaves this API as "
        f"{PROBLEM_MEDIA_TYPE}, so a client cannot be expected to parse this one."
    )
    body: dict[str, object] = response.json()
    assert body["status"] == response.status_code, (
        f"The problem document claims status {body['status']} while the response carries "
        f"{response.status_code}."
    )
    return body


def problem_code(response: Response) -> str:
    """Return the stable slug at the end of the problem type."""
    return str(problem_of(response)["type"]).rsplit(PROBLEM_TYPE_SEPARATOR, 1)[-1]


def future_period(
    *, days_ahead: int = DEFAULT_DAYS_AHEAD, hire_days: int = DEFAULT_HIRE_DAYS
) -> BookingPeriod:
    """Return a hire period inside the booking horizon.

    The reservation use case refuses a hire that starts in the past, so an API
    test cannot use the fixed dates the database tests use.

    Args:
        days_ahead: How far ahead the hire starts.
        hire_days: How many chargeable days it runs for.

    """
    start = date.today() + timedelta(days=days_ahead)
    return BookingPeriod(start, start + timedelta(days=hire_days))


def booking_payload(
    *,
    product_model_id: UUID,
    branch_id: UUID,
    period: BookingPeriod,
    quantity: int = DEFAULT_QUANTITY,
) -> dict[str, object]:
    """Return the booking body in the camelCase names the React client posts."""
    return {
        "productModelId": str(product_model_id),
        "branchId": str(branch_id),
        "startDate": period.start.isoformat(),
        "endDate": period.end.isoformat(),
        "quantity": quantity,
    }


__all__ = ["booking_payload", "future_period", "problem_code", "problem_of"]
