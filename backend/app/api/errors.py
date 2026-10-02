"""Exception handlers and the RFC 9457 problem mapping.

Every error leaves this application as a problem document with the media type
`application/problem+json`. That includes the ones nobody planned for: a
catch all handler is registered for `Exception`, so an unhandled fault is
logged with its traceback on the server and answered with a generic 500 body
that carries no stack trace, no SQL and no file path.

The mapping from a domain error to a status code lives here and nowhere else.
The domain raises meaning, the HTTP layer chooses a number.

A refused field is always reported the same way, under `errors.fields`, keyed
by where the value came from and its name on the wire, for example
`query.from`. That holds whether the framework refused the value for its type
or a read refused it for breaking a rule, so a client reads one shape.

Every problem document carries the request id as `requestId`. The same value
is in the `X-Request-ID` response header and on every log record of the
request, which is what makes the sentence in the generic 500 body true.

In the deployed application the request middleware is the one that catches an
unhandled fault, because it has to send the 500 through itself for the response
to carry the request id and the security headers. It calls
`handle_unexpected_error` to do so. The same function is still registered for
`Exception` below, so an application assembled without that middleware answers
with the same document.

Two refusals carry something beside the document. A throttled caller is told
how long to wait in `Retry-After`. A refused refresh clears the refresh cookie,
so the browser stops presenting a token that no longer works.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.refresh_cookie import refresh_cookie_of
from app.api.schemas import ProblemDetail
from app.application.refusal import refused_parameter_of
from app.domain.errors import (
    AccountOnHoldError,
    AllocationConflictError,
    AuthenticationFailure,
    AuthorisationFailure,
    BranchScopeError,
    DomainError,
    InactiveAccount,
    InvalidCredentials,
    NotFound,
    OriginNotAllowed,
    SessionExpired,
    StateTransitionError,
    TooManyAttempts,
    ValidationFailure,
)
from app.request_context import current_request_id

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "https://toolshedhire.co.za/problems/"
REQUEST_VALIDATION_CODE = "request-validation-failure"
REQUEST_VALIDATION_DETAIL = "The request body or query string did not pass validation."
# Where a refused read parameter came from. Every read takes its parameters
# from the query string, and FastAPI names its own refusals the same way.
QUERY_LOCATION = "query"
RETRY_AFTER_HEADER = "Retry-After"

# One entry per domain error. A domain error absent from this table would fall
# through to the catch all and be reported as a 500, so the table is total.
DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    ValidationFailure: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NotFound: status.HTTP_404_NOT_FOUND,
    AuthenticationFailure: status.HTTP_401_UNAUTHORIZED,
    InvalidCredentials: status.HTTP_401_UNAUTHORIZED,
    SessionExpired: status.HTTP_401_UNAUTHORIZED,
    TooManyAttempts: status.HTTP_429_TOO_MANY_REQUESTS,
    OriginNotAllowed: status.HTTP_403_FORBIDDEN,
    AuthorisationFailure: status.HTTP_403_FORBIDDEN,
    InactiveAccount: status.HTTP_403_FORBIDDEN,
    BranchScopeError: status.HTTP_403_FORBIDDEN,
    AccountOnHoldError: status.HTTP_403_FORBIDDEN,
    AllocationConflictError: status.HTTP_409_CONFLICT,
    StateTransitionError: status.HTTP_409_CONFLICT,
}

# Returned to the caller in place of any unhandled exception detail. The
# correlation id it mentions is the `requestId` member of the same document.
GENERIC_SERVER_ERROR_DETAIL = (
    "The request could not be completed because of an unexpected server fault. "
    "The fault has been logged with a correlation id."
)


def problem_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    detail: str,
    errors: dict[str, object] | None = None,
) -> JSONResponse:
    """Build a problem document response.

    Args:
        request: The request being answered, used for the `instance` member.
        status_code: The HTTP status to return.
        code: The stable slug identifying the kind of problem.
        detail: A sentence describing this occurrence.
        errors: Optional structured context, safe to disclose to the caller.

    Returns:
        The response, with the id of the current request as `requestId` when
        the request middleware is installed.

    """
    problem = ProblemDetail(
        type=f"{PROBLEM_TYPE_PREFIX}{code}",
        title=HTTPStatus(status_code).phrase,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
        errors=errors,
        request_id=current_request_id(),
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True, by_alias=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def validation_problem(request: Request, fields: dict[str, str]) -> JSONResponse:
    """Build the 422 that names each refused field under `errors.fields`.

    A field is named by where its value came from and what it is called on the
    wire, for example `query.from`. There is one shape for every refused
    field, whether the framework refused it for its type or a rule refused it
    for its value, so a client needs one reader.
    """
    logger.info(
        "api.request_validation_failed",
        extra={"path": request.url.path, "method": request.method, "fields": fields},
    )
    return problem_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=REQUEST_VALIDATION_CODE,
        detail=REQUEST_VALIDATION_DETAIL,
        errors={"fields": fields},
    )


async def handle_domain_error(request: Request, exc: Exception) -> Response:
    """Map a domain error to its status code and a problem document.

    A validation failure that names the query parameter it refused is answered
    in the shape of a request validation failure, with its sentence under that
    parameter.
    """
    if not isinstance(exc, DomainError):
        raise exc
    refused_parameter = refused_parameter_of(exc) if isinstance(exc, ValidationFailure) else None
    if refused_parameter is not None:
        return validation_problem(request, {f"{QUERY_LOCATION}.{refused_parameter}": exc.message})
    status_code = DOMAIN_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    log = logger.warning if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR else logger.error
    log(
        "api.domain_error",
        extra={
            "code": exc.code,
            "status": status_code,
            "path": request.url.path,
            "method": request.method,
            "error_message": exc.message,
            "detail": exc.detail,
        },
    )
    response = problem_response(
        request=request,
        status_code=status_code,
        code=exc.code,
        detail=exc.message,
        errors=dict(exc.detail) or None,
    )
    if isinstance(exc, TooManyAttempts):
        response.headers[RETRY_AFTER_HEADER] = str(exc.retry_after_seconds)
    if isinstance(exc, SessionExpired):
        cookie = refresh_cookie_of(request)
        if cookie is not None:
            cookie.clear_on(response)
    return response


async def handle_http_exception(request: Request, exc: Exception) -> Response:
    """Render FastAPI's own HTTPException as a problem document."""
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    logger.info(
        "api.http_exception",
        extra={
            "status": exc.status_code,
            "path": request.url.path,
            "method": request.method,
            "detail": str(exc.detail),
        },
    )
    return problem_response(
        request=request,
        status_code=exc.status_code,
        code="http-error",
        detail=str(exc.detail),
    )


async def handle_request_validation_error(request: Request, exc: Exception) -> Response:
    """Render a request validation failure as a 422 problem document."""
    if not isinstance(exc, RequestValidationError):
        raise exc
    fields = {
        ".".join(str(part) for part in error.get("loc", ())): str(error.get("msg", ""))
        for error in exc.errors()
    }
    return validation_problem(request, fields)


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Log an unhandled exception in full and answer with a bare 500.

    The traceback goes to the log, never to the client. A stack trace in a
    response body is a free map of the application for anyone probing it. The
    log record and the response body carry the same request id, so the caller
    can quote one value and I can find the traceback it belongs to.
    """
    logger.exception(
        "api.unhandled_exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
        },
    )
    return problem_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal-server-error",
        detail=GENERIC_SERVER_ERROR_DETAIL,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler to the application.

    Registered from the most specific to the least, ending with the catch all
    for `Exception`, so no code path can return an unformatted 500.
    """
    handlers: list[tuple[type[Exception], Callable[[Request, Exception], Awaitable[Response]]]] = [
        (DomainError, handle_domain_error),
        (RequestValidationError, handle_request_validation_error),
        (StarletteHTTPException, handle_http_exception),
        (Exception, handle_unexpected_error),
    ]
    for exception_type, handler in handlers:
        app.add_exception_handler(exception_type, handler)
    logger.info(
        "api.exception_handlers_registered",
        extra={"handler_count": len(handlers)},
    )
