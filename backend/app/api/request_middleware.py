"""The request id and the access log.

This middleware does three things for every HTTP request.

1. It gives the request an id. A valid UUID in the incoming `X-Request-ID`
   header is kept, so a caller or a proxy can supply its own. Anything else is
   replaced by a new UUID4. The id is returned in the `X-Request-ID` response
   header, stamped on every log record and quoted in every problem document.
   The address of the client is kept beside it, for the audit trail.
2. It writes one access log line when the response is finished, with the
   method, the route template, the status, the duration, the role of the caller
   and the outcome.
3. It is the last place an unhandled fault can be caught while the request id
   is still known, so it answers such a fault with the generic 500 problem
   document.

It is written as plain ASGI and not on `BaseHTTPMiddleware`. It changes the
headers of the message that starts the response and passes every body message
on untouched, so nothing is buffered. It also runs in the same task as the
handler, which is what lets the context variable it binds be seen there.

The route in the access log is the template, for example
`/api/reservations/{reservation_id}`, and never the path that was requested. A
path holds identifiers, and a log that can be grouped by endpoint is worth more
than one that cannot.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Final

from fastapi import Request, status
from fastapi.routing import iter_route_contexts
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import handle_unexpected_error
from app.request_context import (
    RequestContext,
    bind_request_context,
    release_request_context,
    resolve_client_address,
    resolve_request_id,
)

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
ACCESS_LOG_EVENT: Final[str] = "http.request_completed"
# Logged as the route when no route matched, which is every 404 for a path the
# application does not serve. The requested path is deliberately not used.
UNMATCHED_ROUTE: Final[str] = "unmatched"

OUTCOME_SUCCESS: Final[str] = "success"
OUTCOME_CLIENT_ERROR: Final[str] = "client_error"
OUTCOME_SERVER_ERROR: Final[str] = "server_error"

HTTP_SCOPE_TYPE: Final[str] = "http"
RESPONSE_START_MESSAGE: Final[str] = "http.response.start"
MILLISECONDS_PER_SECOND: Final[int] = 1000
DURATION_DECIMAL_PLACES: Final[int] = 2


@dataclass
class _Exchange:
    """What the middleware learns about one response while it is being sent."""

    status_code: int | None = None
    faulted: bool = False


class RouteTemplates:
    """Look up the full path template of the route a request matched.

    The router records the matched route in the scope, but a route only knows
    the path it was declared with. The prefixes of the routers it was included
    through are known to the application, so the templates are read once from
    the application's route table and kept by the identity of each route. The
    routes live as long as the application, so the identities stay valid.
    """

    def __init__(self) -> None:
        """Start with no table. It is built on the first request."""
        self._templates: dict[int, str] | None = None

    def template_for(self, scope: Scope) -> str:
        """Return the template of the matched route, or `UNMATCHED_ROUTE`.

        Args:
            scope: The ASGI scope after the application has handled the
                request, which is when the router has recorded its match.

        """
        matched = scope.get("route")
        if matched is None:
            matched = scope.get("endpoint")
        if matched is None:
            return UNMATCHED_ROUTE
        if self._templates is None:
            self._templates = self._read_templates(scope)
        return self._templates.get(id(matched), UNMATCHED_ROUTE)

    @staticmethod
    def _read_templates(scope: Scope) -> dict[int, str]:
        """Read every route of the application into a table keyed by identity."""
        templates: dict[int, str] = {}
        for context in iter_route_contexts(scope["app"].routes):
            template = context.path_format
            if template is None:
                continue
            route = context.original_route
            templates[id(route)] = template
            # A route that is not an API route, such as the documentation
            # pages, is recorded in the scope by its endpoint alone.
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None:
                templates.setdefault(id(endpoint), template)
        logger.debug("http.route_templates_read", extra={"route_count": len(templates)})
        return templates


def _client_host_of(scope: Scope) -> str | None:
    """Return the host the server recorded for the client, if it recorded one.

    The server fills `client` with a host and a port. Started with its proxy
    headers option, as the container is, it has already replaced the host with
    the address the platform forwarded.
    """
    client = scope.get("client")
    if not client:
        return None
    return str(client[0])


def outcome_of(status_code: int | None, *, faulted: bool) -> str:
    """Classify a finished request for the access log.

    Args:
        status_code: The status code that was sent, or None when the
            application finished without starting a response.
        faulted: True when an unhandled fault was caught, whatever was sent.

    """
    if faulted or status_code is None:
        return OUTCOME_SERVER_ERROR
    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return OUTCOME_SERVER_ERROR
    if status_code >= status.HTTP_400_BAD_REQUEST:
        return OUTCOME_CLIENT_ERROR
    return OUTCOME_SUCCESS


LEVEL_BY_OUTCOME: Final[dict[str, int]] = {
    OUTCOME_SUCCESS: logging.INFO,
    OUTCOME_CLIENT_ERROR: logging.WARNING,
    OUTCOME_SERVER_ERROR: logging.ERROR,
}


class RequestContextMiddleware:
    """Bind a request id, write the access log and catch unhandled faults."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application in the stack."""
        self.app = app
        self._route_templates = RouteTemplates()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request with a request id bound for its whole life."""
        if scope["type"] != HTTP_SCOPE_TYPE:
            await self.app(scope, receive, send)
            return

        context = RequestContext(
            request_id=resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER)),
            client_address=resolve_client_address(_client_host_of(scope)),
        )
        exchange = _Exchange()
        started_at = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            """Add the request id to the head of the response and pass it on."""
            if message["type"] == RESPONSE_START_MESSAGE:
                exchange.status_code = int(message["status"])
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = context.request_id
            await send(message)

        token = bind_request_context(context)
        try:
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as exc:
                # The handler logs the fault in full. While no response has
                # started it is answered here with the generic 500. Once one
                # has, there is nothing left to send, and the server ends the
                # connection if the body was cut short. Either way it is not
                # re-raised, because the catch all outside this middleware
                # would log it a second time without the request id.
                exchange.faulted = True
                failure = await handle_unexpected_error(Request(scope), exc)
                if exchange.status_code is None:
                    await failure(scope, receive, send_with_request_id)
            self._write_access_log(scope, context, exchange, started_at)
        finally:
            release_request_context(token)

    def _write_access_log(
        self,
        scope: Scope,
        context: RequestContext,
        exchange: _Exchange,
        started_at: float,
    ) -> None:
        """Write the one access log line of a finished request."""
        outcome = outcome_of(exchange.status_code, faulted=exchange.faulted)
        elapsed_ms = (time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND
        logger.log(
            LEVEL_BY_OUTCOME[outcome],
            ACCESS_LOG_EVENT,
            extra={
                "method": scope["method"],
                "route": self._route_templates.template_for(scope),
                "status": exchange.status_code,
                "duration_ms": round(elapsed_ms, DURATION_DECIMAL_PLACES),
                "actor_role": context.actor_role,
                "outcome": outcome,
                "request_id": context.request_id,
            },
        )


__all__ = [
    "ACCESS_LOG_EVENT",
    "OUTCOME_CLIENT_ERROR",
    "OUTCOME_SERVER_ERROR",
    "OUTCOME_SUCCESS",
    "REQUEST_ID_HEADER",
    "UNMATCHED_ROUTE",
    "RequestContextMiddleware",
    "RouteTemplates",
    "outcome_of",
]
