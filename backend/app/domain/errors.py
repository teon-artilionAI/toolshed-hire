"""Domain errors.

These carry no HTTP concepts. The API layer owns the mapping from a domain
error to a status code and an RFC 9457 problem document, which keeps the domain
usable from a test, a script or a future worker with no HTTP anywhere in sight.

Every error carries structured detail rather than only a sentence, so the log
line and the problem response can both be built without parsing prose.
"""

from __future__ import annotations

from uuid import UUID

# The value type accepted in the structured detail bag. Deliberately narrow so
# a detail can always be serialised into a JSON problem document.
type DetailValue = str | int | float | bool | None | list[str]


class DomainError(Exception):
    """Base class for every error the domain raises deliberately.

    Attributes:
        message: A sentence describing what was attempted and what went wrong.
        code: A stable machine readable slug, used as the problem type suffix.
        detail: Structured context, safe to return to an authenticated caller.

    """

    code = "domain-error"

    def __init__(self, message: str, detail: dict[str, DetailValue] | None = None) -> None:
        """Store the message and the structured detail bag."""
        super().__init__(message)
        self.message = message
        self.detail: dict[str, DetailValue] = detail or {}


class ValidationFailure(DomainError):
    """A caller supplied input the domain refuses, such as a reversed period."""

    code = "validation-failure"


class NotFound(DomainError):
    """A referenced record does not exist, or the caller may not see that it does."""

    code = "not-found"


class AuthenticationFailure(DomainError):
    """Credentials were absent, malformed, expired or wrong."""

    code = "authentication-failure"


class AuthorisationFailure(DomainError):
    """The caller is known but the role or branch scope does not permit the action."""

    code = "authorisation-failure"


class InactiveAccount(DomainError):
    """A token named an account that has since been deactivated."""

    code = "inactive-account"


class InvalidCredentials(DomainError):
    """A sign in was refused, and the caller is not told which part was wrong.

    A wrong password, an unknown address, a locked account and a deactivated
    account all raise this with the same message and no detail, so the four
    cannot be told apart from outside (BR-46). The reason is written to the
    log and to the audit trail on the server. The API maps this to HTTP 401.
    """

    code = "invalid-credentials"


class SessionExpired(DomainError):
    """A refresh token was absent, unknown, expired, revoked or already used.

    The five cases are answered alike, because a caller holding a token that
    no longer works needs one instruction, which is to sign in again. The API
    maps this to HTTP 401.
    """

    code = "session-expired"


class TooManyAttempts(DomainError):
    """A caller exceeded a rate limit and must wait for the window to end.

    The API maps this to HTTP 429 and sends the wait as `Retry-After`.
    """

    code = "too-many-attempts"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        """Build the refusal with the number of seconds until the window ends."""
        super().__init__(message, {"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class OriginNotAllowed(DomainError):
    """A request authenticated by a cookie came from an origin that is not this site.

    The API maps this to HTTP 403.
    """

    code = "origin-not-allowed"


class AllocationConflictError(DomainError):
    """No asset could be held for the requested product model, branch and period.

    Raised both when the pre check finds too few free units and when the
    database exclusion constraint rejects an insert. The second case is the one
    that matters, because it is the only path that is correct under two
    genuinely concurrent transactions. The API maps this to HTTP 409.

    The class carries the name the design document gives it. The problem slug
    stays `asset-unavailable`, because the slug is what a client reads and
    renaming a class is no reason to change what goes over the wire.
    """

    code = "asset-unavailable"

    def __init__(
        self,
        message: str,
        *,
        product_model_id: UUID | None = None,
        branch_id: UUID | None = None,
        period: str | None = None,
        requested_quantity: int | None = None,
        available_quantity: int | None = None,
        constraint_name: str | None = None,
        asset_tag: str | None = None,
    ) -> None:
        """Build the conflict with everything a caller needs to retry sensibly."""
        detail: dict[str, DetailValue] = {
            "product_model_id": str(product_model_id) if product_model_id else None,
            "branch_id": str(branch_id) if branch_id else None,
            "period": period,
            "requested_quantity": requested_quantity,
            "available_quantity": available_quantity,
            "constraint_name": constraint_name,
            "asset_tag": asset_tag,
        }
        # Annotated rather than inferred. Without it the comprehension narrows
        # the value type to the non None union, and dict is invariant in its
        # value type, so the narrower dict is not accepted where a
        # dict[str, DetailValue] is expected.
        present: dict[str, DetailValue] = {
            key: value for key, value in detail.items() if value is not None
        }
        super().__init__(message, present)


class StateTransitionError(DomainError):
    """A reservation was asked to make a move its current status does not permit.

    The reservation states that raise this arrive with the booking lifecycle.
    The error is defined now so the HTTP mapping is complete before the first
    state exists. The API maps it to HTTP 409, because the request was well
    formed and lost to the state the booking is already in.
    """

    code = "state-transition"

    def __init__(self, message: str, *, from_status: str, to_status: str) -> None:
        """Build the error naming the status held and the status asked for."""
        super().__init__(message, {"from_status": from_status, "to_status": to_status})
        self.from_status = from_status
        self.to_status = to_status


class BranchScopeError(DomainError):
    """A branch scoped account reached for a record that belongs to another branch.

    Counter staff act for one branch only. The API maps this to HTTP 403.
    """

    code = "branch-scope"


class AccountOnHoldError(DomainError):
    """A customer whose account is on hold tried to book (BR-18).

    The API maps this to HTTP 403. The customer is known and the request is
    valid, and the answer is still no until the branch lifts the hold.
    """

    code = "account-on-hold"
