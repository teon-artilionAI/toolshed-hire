"""The Have I Been Pwned adapter, against a mock transport.

No request leaves the process. The handler stands where the network would be,
so the adapter is exercised up to the socket. The prefix sent is the first five
characters of the password SHA-1 digest, the answer is matched on the rest, and
the padding header is always sent.

When the service fails, the adapter answers False and logs the warning the
alert policy in B3.2 counts. A third party outage must not stop a password
being chosen.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Final

import httpx

from app.infrastructure.breach_check import (
    ADD_PADDING_HEADER,
    RANGE_URL,
    TIMEOUT_REASON,
    UNAVAILABLE_REASON,
    HttpBreachedPasswordChecker,
)
from tests.support.log_capture import LogCapture

PASSWORD: Final[str] = "correct-horse-battery-staple"
DIGEST: Final[str] = hashlib.sha1(PASSWORD.encode("utf-8")).hexdigest().upper()
PREFIX: Final[str] = DIGEST[:5]
SUFFIX: Final[str] = DIGEST[5:]
OTHER_SUFFIX: Final[str] = "0" * 35
RANGE_BODY: Final[str] = f"{SUFFIX}:12345\r\n{OTHER_SUFFIX}:1\r\n"

type Handler = Callable[[httpx.Request], httpx.Response]


def checker_for(handler: Handler) -> HttpBreachedPasswordChecker:
    """Return the adapter wired to a mock transport in place of the network."""
    return HttpBreachedPasswordChecker(transport=httpx.MockTransport(handler))


def answering(body: str) -> tuple[HttpBreachedPasswordChecker, list[httpx.Request]]:
    """Return a checker whose service answers `body`, and the requests it saw."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=body)

    return checker_for(handler), requests


def test_a_listed_password_is_breached() -> None:
    """A suffix in the answer is a match, whatever its count."""
    checker, _requests = answering(RANGE_BODY)
    assert checker.is_breached(PASSWORD) is True


def test_an_unlisted_password_is_not_breached() -> None:
    """A suffix absent from the answer is not a match."""
    checker, _requests = answering("00000000000000000000000000000000000:1\r\n")
    assert checker.is_breached(PASSWORD) is False


def test_only_the_prefix_leaves_the_process_and_padding_is_asked_for() -> None:
    """The request carries the first five characters and the padding header."""
    checker, requests = answering(RANGE_BODY)
    checker.is_breached(PASSWORD)
    (request,) = requests
    assert str(request.url) == f"{RANGE_URL}{PREFIX}"
    assert request.headers[ADD_PADDING_HEADER] == "true"
    assert PASSWORD not in str(request.url)


def test_a_timeout_is_not_a_breach_and_is_warned_about(
    application_log: LogCapture,
) -> None:
    """A slow service accepts the password and says why in the log."""

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("the service did not answer", request=request)

    assert checker_for(timeout).is_breached(PASSWORD) is False
    entry = application_log.only("auth.breach_check_unavailable")
    assert entry["reason"] == TIMEOUT_REASON


def test_a_service_error_is_not_a_breach_and_is_warned_about(
    application_log: LogCapture,
) -> None:
    """A refused request accepts the password and says why in the log."""

    def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="not now")

    assert checker_for(unavailable).is_breached(PASSWORD) is False
    entry = application_log.only("auth.breach_check_unavailable")
    assert entry["reason"] == UNAVAILABLE_REASON
