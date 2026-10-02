"""What I know about the request being served.

Every request gets one `RequestContext`, held in a context variable from the
moment the middleware accepts the request until the response is finished. The
logging filter reads the request id from it, the problem documents quote it,
and the authentication dependency writes the role of the caller into it so the
access log can report who made the request without a second database query.

The variable holds one mutable object and I change that object in place rather
than setting the variable again. FastAPI runs a synchronous dependency in a
worker thread with a copy of the context. A value set inside that copy never
reaches the middleware. A change to the object both copies point at does.

This module sits beside the logging configuration and outside the four layers,
because the logging filter and the HTTP layer both need it and neither should
import the other to get it.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Final
from uuid import UUID, uuid4

# The role recorded for a request nobody has authenticated.
ANONYMOUS_ACTOR_ROLE: Final[str] = "anonymous"

CONTEXT_VARIABLE_NAME: Final[str] = "toolshed_request_context"


@dataclass
class RequestContext:
    """The facts about one request that outlive any single function call.

    Attributes:
        request_id: The canonical UUID that correlates the response, the
            problem document and every log record of this request.
        actor_role: The stored role of the authenticated caller, or
            `ANONYMOUS_ACTOR_ROLE` while nobody has been authenticated.

    """

    request_id: str
    actor_role: str = ANONYMOUS_ACTOR_ROLE


_current_request: ContextVar[RequestContext | None] = ContextVar(
    CONTEXT_VARIABLE_NAME, default=None
)


def resolve_request_id(candidate: str | None) -> str:
    """Return the request id to use for a request.

    Args:
        candidate: The value of the incoming `X-Request-ID` header, if any.

    Returns:
        The candidate in canonical form when it is a valid UUID, and a new
        UUID4 otherwise. The caller's value is never echoed as it arrived, so
        nothing but thirty two hexadecimal digits and four hyphens can reach a
        response header or a log line through this path.

    """
    supplied = _parse_uuid(candidate) if candidate else None
    return str(supplied if supplied is not None else uuid4())


def _parse_uuid(candidate: str) -> UUID | None:
    """Return the UUID a header value spells, or None when it spells none.

    A value that is not a UUID is an expected input and not a fault, so it is
    answered with None. I do not log the rejected value, because the caller
    chooses it and it would be a way to write arbitrary text into the log.
    """
    try:
        return UUID(candidate.strip())
    except ValueError:
        return None


def bind_request_context(context: RequestContext) -> Token[RequestContext | None]:
    """Make `context` the current request and return the token that undoes it."""
    return _current_request.set(context)


def release_request_context(token: Token[RequestContext | None]) -> None:
    """Restore whatever was current before `bind_request_context` was called."""
    _current_request.reset(token)


def current_request_id() -> str | None:
    """Return the id of the request being served, or None outside a request."""
    context = _current_request.get()
    return context.request_id if context is not None else None


def record_actor_role(role: str) -> None:
    """Record the role of the caller the request was authenticated as.

    Outside a request there is nothing to record against, so the call does
    nothing. That keeps the authentication dependency usable from an
    application assembled without the request middleware.

    Args:
        role: The stored role value, for example `COUNTER_STAFF`.

    """
    context = _current_request.get()
    if context is not None:
        context.actor_role = role
