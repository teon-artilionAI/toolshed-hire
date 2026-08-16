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
    """The account exists and the password matched, but the account is deactivated."""

    code = "inactive-account"


class AssetUnavailableConflict(DomainError):
    """No asset could be held for the requested product model, branch and period.

    Raised both when the pre check finds too few free units and when the
    database exclusion constraint rejects an insert. The second case is the one
    that matters, because it is the only path that is correct under two
    genuinely concurrent transactions. The API maps this to HTTP 409.
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
    ) -> None:
        """Build the conflict with everything a caller needs to retry sensibly."""
        detail: dict[str, DetailValue] = {
            "product_model_id": str(product_model_id) if product_model_id else None,
            "branch_id": str(branch_id) if branch_id else None,
            "period": period,
            "requested_quantity": requested_quantity,
            "available_quantity": available_quantity,
            "constraint_name": constraint_name,
        }
        # Annotated rather than inferred. Without it the comprehension narrows
        # the value type to the non None union, and dict is invariant in its
        # value type, so the narrower dict is not accepted where a
        # dict[str, DetailValue] is expected.
        present: dict[str, DetailValue] = {
            key: value for key, value in detail.items() if value is not None
        }
        super().__init__(message, present)
