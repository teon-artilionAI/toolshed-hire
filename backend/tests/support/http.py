"""Helpers for reading what the HTTP boundary actually said.

Two things are checked here rather than in every test. A problem document must
arrive as `application/problem+json`, because a correct status code served with
the wrong media type is a contract violation no status assertion would catch.
And the status in the body must match the status on the response, because a
document that disagrees with its own envelope is worse than no document.

The bodies the reservation routes are sent are built in
`tests/support/booking_api.py`.
"""

from __future__ import annotations

import logging
from typing import Final

from httpx import Response

from app.api.errors import PROBLEM_MEDIA_TYPE

logger = logging.getLogger(__name__)

PROBLEM_TYPE_SEPARATOR: Final[str] = "/"


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


__all__ = ["problem_code", "problem_of"]
