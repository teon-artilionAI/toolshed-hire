"""The layered authorisation dependency chain.

Four layers, each building on the one before it.

1. `get_bearer_token` pulls the credential out of the Authorization header.
2. `get_authenticated_user` verifies the token and loads the account.
3. `get_active_user` refuses a deactivated account.
4. `require_roles` refuses an account whose role is not in the allowed set.

The role is read from the database row on every request, never from a token
claim. An access token minted before a demotion therefore stops granting the
old permissions the moment the row changes, rather than at expiry.

Every endpoint must depend on one of the role dependencies. An endpoint with no
declared policy is a defect (BR-41), and the route policy test in the test
suite is what makes that statement enforceable rather than aspirational.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.domain.enums import UserRole
from app.domain.errors import AuthenticationFailure, AuthorisationFailure, InactiveAccount
from app.infrastructure.database import get_session
from app.infrastructure.models import Branch, UserAccount
from app.infrastructure.security import read_subject

logger = logging.getLogger(__name__)

AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "

SessionDependency = Annotated[Session, Depends(get_session)]


def get_bearer_token(request: Request) -> str:
    """Extract the bearer token from the Authorization header.

    Raises:
        AuthenticationFailure: If the header is absent or not a bearer scheme.

    """
    header_value = request.headers.get(AUTHORIZATION_HEADER)
    if not header_value:
        raise AuthenticationFailure(
            "Attempted to reach a protected endpoint without an Authorization header.",
            {"reason": "missing-credentials"},
        )
    if not header_value.startswith(BEARER_PREFIX):
        raise AuthenticationFailure(
            "Attempted to authenticate with an unsupported authorization scheme. "
            "Expected a Bearer token.",
            {"reason": "unsupported-scheme"},
        )
    token = header_value[len(BEARER_PREFIX) :].strip()
    if not token:
        raise AuthenticationFailure(
            "Attempted to authenticate with an empty Bearer token.",
            {"reason": "empty-credentials"},
        )
    return token


TokenDependency = Annotated[str, Depends(get_bearer_token)]


def get_authenticated_user(token: TokenDependency, session: SessionDependency) -> UserAccount:
    """Verify the token and load the account it identifies.

    Raises:
        AuthenticationFailure: If the token fails verification, or if it names
            an account that no longer exists. The two cases are deliberately
            answered identically, so a caller cannot probe for valid ids.

    """
    user_id = read_subject(token)
    account = session.get(UserAccount, user_id)
    if account is None:
        logger.warning(
            "auth.token_subject_not_found",
            extra={"user_id": str(user_id), "attempted": "load account named by token subject"},
        )
        raise AuthenticationFailure(
            "Attempted to authenticate with a token whose subject does not name an account.",
            {"reason": "unknown-subject"},
        )
    logger.debug("auth.user_loaded", extra={"user_id": str(account.id), "role": account.role.value})
    return account


AuthenticatedUser = Annotated[UserAccount, Depends(get_authenticated_user)]


def get_active_user(user: AuthenticatedUser) -> UserAccount:
    """Refuse a deactivated account.

    Accounts are deactivated, never deleted, so a valid token can outlive the
    holder's access. This layer is what closes that window.

    Raises:
        InactiveAccount: If `is_active` is false on the loaded row.

    """
    if not user.is_active:
        logger.warning(
            "auth.inactive_account_rejected",
            extra={"user_id": str(user.id), "role": user.role.value},
        )
        raise InactiveAccount(
            f"Account {user.email} is deactivated and may not perform any action. "
            "An administrator can reactivate it.",
            {"reason": "account-deactivated"},
        )
    return user


ActiveUser = Annotated[UserAccount, Depends(get_active_user)]


def require_roles(*allowed: UserRole) -> Callable[[UserAccount], UserAccount]:
    """Build a dependency that admits only the listed roles.

    Args:
        allowed: The roles permitted to reach the endpoint. Never empty, so an
            endpoint cannot accidentally declare an empty allow list, which
            would read as "any role" to a reader and "no role" to the code.

    Returns:
        A FastAPI dependency returning the account when the role is permitted.

    """
    if not allowed:
        raise ValueError(
            "require_roles was called with no roles. Every endpoint must name the roles "
            "it admits, because the default is deny (BR-41)."
        )
    permitted = frozenset(allowed)

    def dependency(user: ActiveUser) -> UserAccount:
        """Admit the account when its stored role is in the permitted set."""
        if user.role not in permitted:
            logger.warning(
                "auth.role_rejected",
                extra={
                    "user_id": str(user.id),
                    "actual_role": user.role.value,
                    "permitted_roles": sorted(role.value for role in permitted),
                },
            )
            raise AuthorisationFailure(
                f"Account {user.email} holds role {user.role.value}, which is not permitted "
                f"here. This endpoint admits {', '.join(sorted(r.value for r in permitted))}.",
                {"required_roles": sorted(role.value for role in permitted)},
            )
        return user

    return dependency


CustomerUser = Annotated[UserAccount, Depends(require_roles(UserRole.CUSTOMER))]
CounterUser = Annotated[UserAccount, Depends(require_roles(UserRole.COUNTER_STAFF, UserRole.ADMIN))]
AdminUser = Annotated[UserAccount, Depends(require_roles(UserRole.ADMIN))]
AnyRoleUser = Annotated[
    UserAccount,
    Depends(require_roles(UserRole.CUSTOMER, UserRole.COUNTER_STAFF, UserRole.ADMIN)),
]


def branch_code_of(session: Session, user: UserAccount) -> str | None:
    """Return the branch code of a branch scoped account, or None.

    Counter staff carry a branch. Customers and administrators do not, so the
    absence of a code is a fact about the role rather than missing data.
    """
    if user.branch_id is None:
        return None
    branch = session.get(Branch, user.branch_id)
    if branch is None:
        logger.error(
            "auth.branch_missing_for_account",
            extra={
                "user_id": str(user.id),
                "branch_id": str(user.branch_id),
                "attempted": "resolve branch code for a branch scoped account",
            },
        )
        return None
    return branch.code
