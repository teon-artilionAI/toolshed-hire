"""Security headers on every response the API sends (C-06 to C-12).

The API returns JSON and nothing else, so its policy can be as strict as a
policy gets. Nothing may be loaded, nothing may frame a response and no other
origin may read one. The browser never renders an API response as a page, so
these headers cost a legitimate client nothing. They are there for the day a
response is opened directly, or an error page is reflected somewhere it should
not be.

The values are named constants so the tests and this module cannot drift apart.

Two headers are conditional.

`Strict-Transport-Security` is sent only where the service is reached over
HTTPS, which is everywhere except development and test. Sent from a local
plain HTTP server it would be ignored at best.

`Cache-Control: no-store` is sent on every response to a request that carried
an `Authorization` header or a cookie. Such a response was built for one
caller, and no cache between the service and the browser may keep it.

The middleware is plain ASGI. It adds to the message that starts the response
and passes the body through without holding it.
"""

from __future__ import annotations

from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

STRICT_TRANSPORT_SECURITY_HEADER: Final[str] = "Strict-Transport-Security"
# Six months, the value the design document commits to, applied to subdomains.
STRICT_TRANSPORT_SECURITY_VALUE: Final[str] = "max-age=15768000; includeSubDomains"

CONTENT_TYPE_OPTIONS_HEADER: Final[str] = "X-Content-Type-Options"
CONTENT_TYPE_OPTIONS_VALUE: Final[str] = "nosniff"

REFERRER_POLICY_HEADER: Final[str] = "Referrer-Policy"
REFERRER_POLICY_VALUE: Final[str] = "strict-origin-when-cross-origin"

CROSS_ORIGIN_OPENER_POLICY_HEADER: Final[str] = "Cross-Origin-Opener-Policy"
CROSS_ORIGIN_OPENER_POLICY_VALUE: Final[str] = "same-origin"

CROSS_ORIGIN_RESOURCE_POLICY_HEADER: Final[str] = "Cross-Origin-Resource-Policy"
CROSS_ORIGIN_RESOURCE_POLICY_VALUE: Final[str] = "same-origin"

PERMISSIONS_POLICY_HEADER: Final[str] = "Permissions-Policy"
PERMISSIONS_POLICY_VALUE: Final[str] = "geolocation=(), microphone=(), camera=(), payment=()"

CONTENT_SECURITY_POLICY_HEADER: Final[str] = "Content-Security-Policy"
CONTENT_SECURITY_POLICY_VALUE: Final[str] = "default-src 'none'; frame-ancestors 'none'"

CACHE_CONTROL_HEADER: Final[str] = "Cache-Control"
CACHE_CONTROL_NO_STORE_VALUE: Final[str] = "no-store"

# A request carrying either of these was made on behalf of one caller.
CREDENTIAL_REQUEST_HEADERS: Final[tuple[str, ...]] = ("Authorization", "Cookie")

# Sent on every response, whatever the environment and whatever the path.
UNCONDITIONAL_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    (CONTENT_TYPE_OPTIONS_HEADER, CONTENT_TYPE_OPTIONS_VALUE),
    (REFERRER_POLICY_HEADER, REFERRER_POLICY_VALUE),
    (CROSS_ORIGIN_OPENER_POLICY_HEADER, CROSS_ORIGIN_OPENER_POLICY_VALUE),
    (CROSS_ORIGIN_RESOURCE_POLICY_HEADER, CROSS_ORIGIN_RESOURCE_POLICY_VALUE),
    (PERMISSIONS_POLICY_HEADER, PERMISSIONS_POLICY_VALUE),
)

HTTP_SCOPE_TYPE: Final[str] = "http"
RESPONSE_START_MESSAGE: Final[str] = "http.response.start"


class SecurityHeadersMiddleware:
    """Add the security headers to the head of every HTTP response."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        strict_transport: bool,
        content_security_policy_exempt_paths: frozenset[str] = frozenset(),
    ) -> None:
        """Wrap the next ASGI application in the stack.

        Args:
            app: The next ASGI application.
            strict_transport: Whether to send `Strict-Transport-Security`. True
                everywhere the service is served over HTTPS.
            content_security_policy_exempt_paths: Exact paths that are answered
                without the content security policy. The interactive
                documentation pages are HTML that loads a script, so the JSON
                only policy would leave them blank. They exist only in
                development and test, and this set is empty everywhere else.

        """
        self.app = app
        self._strict_transport = strict_transport
        self._content_security_policy_exempt_paths = content_security_policy_exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request and add the headers when its response starts."""
        if scope["type"] != HTTP_SCOPE_TYPE:
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        carried_credentials = any(name in request_headers for name in CREDENTIAL_REQUEST_HEADERS)
        policy_applies = scope["path"] not in self._content_security_policy_exempt_paths

        async def send_with_security_headers(message: Message) -> None:
            """Add the headers to the head of the response and pass it on."""
            if message["type"] == RESPONSE_START_MESSAGE:
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in UNCONDITIONAL_HEADERS:
                    headers[name] = value
                if policy_applies:
                    headers[CONTENT_SECURITY_POLICY_HEADER] = CONTENT_SECURITY_POLICY_VALUE
                if self._strict_transport:
                    headers[STRICT_TRANSPORT_SECURITY_HEADER] = STRICT_TRANSPORT_SECURITY_VALUE
                if carried_credentials:
                    headers[CACHE_CONTROL_HEADER] = CACHE_CONTROL_NO_STORE_VALUE
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


__all__ = [
    "CACHE_CONTROL_HEADER",
    "CACHE_CONTROL_NO_STORE_VALUE",
    "CONTENT_SECURITY_POLICY_HEADER",
    "CONTENT_SECURITY_POLICY_VALUE",
    "CONTENT_TYPE_OPTIONS_HEADER",
    "CONTENT_TYPE_OPTIONS_VALUE",
    "CROSS_ORIGIN_OPENER_POLICY_HEADER",
    "CROSS_ORIGIN_OPENER_POLICY_VALUE",
    "CROSS_ORIGIN_RESOURCE_POLICY_HEADER",
    "CROSS_ORIGIN_RESOURCE_POLICY_VALUE",
    "PERMISSIONS_POLICY_HEADER",
    "PERMISSIONS_POLICY_VALUE",
    "REFERRER_POLICY_HEADER",
    "REFERRER_POLICY_VALUE",
    "STRICT_TRANSPORT_SECURITY_HEADER",
    "STRICT_TRANSPORT_SECURITY_VALUE",
    "SecurityHeadersMiddleware",
]
