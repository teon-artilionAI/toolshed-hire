"""Exception handlers and the RFC 9457 problem mapping.

Every error leaves this application as a problem document with the media type
`application/problem+json`. That includes the ones nobody planned for: a
catch all handler is registered for `Exception`, so an unhandled fault is
logged with its traceback on the server and answered with a generic 500 body
that carries no stack trace, no SQL and no file path.

The mapping from a domain error to a status code lives here and nowhere else.
The domain raises meaning, the HTTP layer chooses a number.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas import ProblemDetail
from app.domain.errors import (
    AssetUnavailableConflict,
    AuthenticationFailure,
    AuthorisationFailure,
    DomainError,
    InactiveAccount,
    NotFound,
    ValidationFailure,
)

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "https://toolshedhire.co.za/problems/"

# One entry per domain error. A domain error absent from this table would fall
# through to the catch all and be reported as a 500, so the table is total.
DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    ValidationFailure: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NotFound: status.HTTP_404_NOT_FOUND,
    AuthenticationFailure: status.HTTP_401_UNAUTHORIZED,
    AuthorisationFailure: status.HTTP_403_FORBIDDEN,
    InactiveAccount: status.HTTP_403_FORBIDDEN,
    AssetUnavailableConflict: status.HTTP_409_CONFLICT,
}

# Returned to the caller in place of any unhandled exception detail.
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

    """
    problem = ProblemDetail(
        type=f"{PROBLEM_TYPE_PREFIX}{code}",
        title=HTTPStatus(status_code).phrase,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def handle_domain_error(request: Request, exc: Exception) -> Response:
    """Map a domain error to its status code and a problem document."""
    if not isinstance(exc, DomainError):
        raise exc
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
    return problem_response(
        request=request,
        status_code=status_code,
        code=exc.code,
        detail=exc.message,
        errors=dict(exc.detail) or None,
    )


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
    logger.info(
        "api.request_validation_failed",
        extra={"path": request.url.path, "method": request.method, "fields": fields},
    )
    return problem_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="request-validation-failure",
        detail="The request body or query string did not pass validation.",
        errors={"fields": fields},
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Log an unhandled exception in full and answer with a bare 500.

    The traceback goes to the log, never to the client. A stack trace in a
    response body is a free map of the application for anyone probing it.
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
