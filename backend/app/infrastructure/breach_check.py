"""Checking a chosen password against Have I Been Pwned (R-14, C-18).

Only the first five hexadecimal characters of the password's SHA-1 digest are
sent. The service answers with every suffix under that prefix and how often
each was seen, and the rest of the comparison happens here. The password itself
and its full digest never leave the process. The `Add-Padding` header makes the
answer a uniform size, so the prefix cannot be guessed from the size of the
response.

The service is a third party. If it is slow or down, the password is accepted
and a warning is logged with the reason, because a registration or a password
reset must not depend on it. The warning is the event B3.2 counts.

The timeout is two seconds. A password is hashed with bcrypt afterwards, which
already takes about a quarter of a second, so the extra wait is bounded.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Final

import httpx

from app.application.identity.ports import BreachedPasswordChecker

logger = logging.getLogger(__name__)

RANGE_URL: Final[str] = "https://api.pwnedpasswords.com/range/"
TIMEOUT_SECONDS: Final[float] = 2.0
PREFIX_LENGTH: Final[int] = 5
ADD_PADDING_HEADER: Final[str] = "Add-Padding"
USER_AGENT: Final[str] = "Toolshed-Hire/1.0 password-safety-check"
TIMEOUT_REASON: Final[str] = "timeout"
UNAVAILABLE_REASON: Final[str] = "service-error"


class HttpBreachedPasswordChecker(BreachedPasswordChecker):
    """Asks the Have I Been Pwned range API, sending only a digest prefix."""

    def __init__(
        self,
        *,
        timeout_seconds: float = TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Keep the timeout and, for a test, the transport that stands in for the network."""
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def is_breached(self, plain_password: str) -> bool:
        """Return True when the service lists the password, and False otherwise."""
        digest = hashlib.sha1(plain_password.encode("utf-8"), usedforsecurity=False).hexdigest()
        prefix, suffix = digest[:PREFIX_LENGTH].upper(), digest[PREFIX_LENGTH:].upper()
        try:
            body = self._fetch_range(prefix)
        except httpx.TimeoutException:
            logger.warning(
                "auth.breach_check_unavailable",
                extra={"reason": TIMEOUT_REASON, "timeout_seconds": self._timeout_seconds},
            )
            return False
        except httpx.HTTPError as error:
            logger.warning(
                "auth.breach_check_unavailable",
                extra={"reason": UNAVAILABLE_REASON, "error": type(error).__name__},
            )
            return False
        return any(
            candidate.strip().upper() == suffix
            for candidate, _separator, _count in (line.partition(":") for line in body.splitlines())
        )

    def _fetch_range(self, prefix: str) -> str:
        """Return the service's answer for one digest prefix."""
        headers = {ADD_PADDING_HEADER: "true", "User-Agent": USER_AGENT}
        with httpx.Client(
            timeout=self._timeout_seconds, transport=self._transport, headers=headers
        ) as client:
            response = client.get(f"{RANGE_URL}{prefix}")
            response.raise_for_status()
            return response.text


__all__ = [
    "ADD_PADDING_HEADER",
    "HttpBreachedPasswordChecker",
    "RANGE_URL",
    "TIMEOUT_SECONDS",
    "TIMEOUT_REASON",
    "UNAVAILABLE_REASON",
]
