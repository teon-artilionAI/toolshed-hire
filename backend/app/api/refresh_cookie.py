"""The refresh cookie and its attributes (C-19).

The refresh token travels in a cookie and nowhere else. The cookie is
`HttpOnly`, so no script can read it. It is `SameSite=Strict`, so no other
site can make the browser send it. Its path is `/api/auth`, so it is sent to
the three session routes and to nothing else the API serves. And it is
`Secure`, so it never crosses plain HTTP.

`Secure` is the one attribute that depends on where the service runs. A
browser will not keep a `Secure` cookie from a local server on plain HTTP, so
it is dropped in development and test and nowhere else.

The header is written out here and not through the framework's cookie helper.
The helper orders the attributes itself and lower cases one of them, and I
want the header to read exactly as the design document states it.

The access token is never put in a cookie. It goes in the response body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import Request, Response

REFRESH_COOKIE_NAME: Final[str] = "toolshed_refresh"
REFRESH_COOKIE_PATH: Final[str] = "/api/auth"
SET_COOKIE_HEADER: Final[str] = "set-cookie"
# The attribute of the application state that holds the cookie writer. The
# application factory sets it once, so the cookie follows the configuration
# the application was built with.
REFRESH_COOKIE_STATE_KEY: Final[str] = "refresh_cookie"
ATTRIBUTE_SEPARATOR: Final[str] = "; "
# A date in the past, for a client that reads Expires and not Max-Age.
EXPIRED_DATE: Final[str] = "Thu, 01 Jan 1970 00:00:00 GMT"


@dataclass(frozen=True, slots=True)
class RefreshCookie:
    """Writes, clears and reads the refresh cookie for one application.

    Attributes:
        secure: Whether the cookie is marked `Secure`. True everywhere the
            service is reached over HTTPS.

    """

    secure: bool

    def header_value(self, token: str, max_age_seconds: int) -> str:
        """Return the `Set-Cookie` value that stores a refresh token.

        Args:
            token: The opaque refresh token.
            max_age_seconds: How long the browser may keep it, which is how
                long the session behind it has left.

        """
        return self._with_attributes(
            f"{REFRESH_COOKIE_NAME}={token}", f"Max-Age={max_age_seconds}"
        )

    def clearing_header_value(self) -> str:
        """Return the `Set-Cookie` value that removes the cookie from the browser."""
        return self._with_attributes(
            f"{REFRESH_COOKIE_NAME}=", "Max-Age=0", f"Expires={EXPIRED_DATE}"
        )

    def set_on(self, response: Response, token: str, max_age_seconds: int) -> None:
        """Add the cookie that stores a refresh token to a response."""
        response.headers.append(SET_COOKIE_HEADER, self.header_value(token, max_age_seconds))

    def clear_on(self, response: Response) -> None:
        """Add the cookie that removes the refresh token to a response."""
        response.headers.append(SET_COOKIE_HEADER, self.clearing_header_value())

    @staticmethod
    def read_from(request: Request) -> str | None:
        """Return the refresh token a request carried, or None when it carried none."""
        return request.cookies.get(REFRESH_COOKIE_NAME) or None

    def _with_attributes(self, *leading: str) -> str:
        """Join the leading parts with the attributes every refresh cookie carries."""
        parts = [*leading, f"Path={REFRESH_COOKIE_PATH}", "HttpOnly"]
        if self.secure:
            parts.append("Secure")
        parts.append("SameSite=Strict")
        return ATTRIBUTE_SEPARATOR.join(parts)


def refresh_cookie_of(request: Request) -> RefreshCookie | None:
    """Return the cookie writer of the application serving a request, or None.

    None means the application was assembled some other way than by
    `create_app`, which is what a bare probe application in the tests is.
    """
    cookie = getattr(request.app.state, REFRESH_COOKIE_STATE_KEY, None)
    return cookie if isinstance(cookie, RefreshCookie) else None
