"""The dependencies of signing in, staying signed in and signing out.

Four things live here.

The first is the identity half of the composition root. `app/api/deps.py`
wires the booking use case. This module wires the three session use cases, and
it is the only place that knows bcrypt and the token signer stand behind the
two ports they take.

The second is the policy of the two routes that are authenticated by a cookie.
A cookie is sent by the browser without the page asking, so `refresh_cookie_access`
checks where the request came from. An `Origin` header, when there is one,
must be one of the configured `CORS_ORIGINS`. A request with no `Origin` is
let through. Some clients leave it off a same origin request, and
`SameSite=Strict` already keeps the cookie off every cross site one.

The third is `require_fresh_roles`, for the actions that must not act on a
stale account. The ordinary chain loads the account once, at the start of the
request. An administrator who waives a charge, changes a role or forces the
release of an allocation is read again, under a row lock, so the role that is
checked is the role that holds until the action commits. Those routes do not
exist yet. When they are added they depend on `FreshAdminUser` and not on
`AdminUser`.

The fourth is the cache policy. A response that carries an access token or
changes a cookie is never stored.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from typing import Annotated, Final

from fastapi import Depends, Request, Response
from sqlmodel import Session, col, select

from app.api.access_policy import REFRESH_COOKIE_POLICY, declare_policy, role_policy
from app.api.deps import (
    AuthenticatedUser,
    ClockDependency,
    SessionDependency,
    UnitOfWorkDependency,
    get_active_user,
    require_roles,
)
from app.api.refresh_cookie import REFRESH_COOKIE_STATE_KEY, RefreshCookie, refresh_cookie_of
from app.api.security_headers import CACHE_CONTROL_HEADER, CACHE_CONTROL_NO_STORE_VALUE
from app.application.identity.ports import AccessTokenIssuer, PasswordVerifier
from app.application.identity.refresh_session import RefreshSessionUseCase
from app.application.identity.sessions import ClientDetails
from app.application.identity.sign_in import LoginThrottleRules, SignInUseCase
from app.application.identity.sign_out import SignOutUseCase
from app.application.throttle import Throttle
from app.config import Settings, settings
from app.domain.enums import UserRole
from app.domain.errors import AuthenticationFailure, OriginNotAllowed
from app.infrastructure.identity_accounts import BcryptPasswordVerifier, JwtAccessTokenIssuer
from app.infrastructure.models import Branch, UserAccount
from app.request_context import current_client_address, record_actor_role

logger = logging.getLogger(__name__)

ORIGIN_HEADER: Final[str] = "origin"
USER_AGENT_HEADER: Final[str] = "user-agent"
# The attribute of the application state that holds the origins a cookie
# request may come from. The application factory sets it once.
ALLOWED_ORIGINS_STATE_KEY: Final[str] = "allowed_origins"
# Mixed with the signing key to make the salt of the throttle, so the salt is
# a secret of the service and needs no setting of its own.
THROTTLE_SALT_PURPOSE: Final[str] = "toolshed-hire-rate-limit-salt"
SALT_ENCODING: Final[str] = "utf-8"
# The caller chooses the Origin header, so only this much of it is logged.
LOGGED_ORIGIN_MAX_LENGTH: Final[int] = 200

_THROTTLE = Throttle(
    salt=hashlib.sha256(
        f"{THROTTLE_SALT_PURPOSE}:{settings.jwt_secret}".encode(SALT_ENCODING)
    ).hexdigest()
)
_PASSWORD_VERIFIER = BcryptPasswordVerifier()
_ACCESS_TOKEN_ISSUER = JwtAccessTokenIssuer()


def login_rules_for(configuration: Settings) -> LoginThrottleRules:
    """Return the two sign in rules with the limits a configuration sets."""
    return LoginThrottleRules.with_limits(
        per_email=configuration.login_attempts_per_email,
        per_address=configuration.login_attempts_per_address,
    )


# Built once, as the module is imported. A limit the throttle cannot use then
# stops the process as it starts and not at the first sign in.
_LOGIN_RULES = login_rules_for(settings)


def normalise_origin(origin: str) -> str:
    """Return an origin in the one form two of them are compared in."""
    return origin.strip().rstrip("/").lower()


def get_refresh_cookie(request: Request) -> RefreshCookie:
    """Return the refresh cookie writer the application was built with.

    Raises:
        RuntimeError: If the application carries none, which means it was
            assembled some other way than by `create_app`.

    """
    cookie = refresh_cookie_of(request)
    if cookie is None:
        raise RuntimeError(
            "Attempted to use the refresh cookie in an application that was built without "
            f"one. Set `app.state.{REFRESH_COOKIE_STATE_KEY}` when the application is "
            "assembled, as `create_app` does."
        )
    return cookie


RefreshCookieDependency = Annotated[RefreshCookie, Depends(get_refresh_cookie)]


def refresh_cookie_access(request: Request) -> None:
    """Admit the holder of a refresh cookie, unless the request came from another site.

    This is the declared policy of the refresh and the sign out routes. It
    does not look at the cookie. The use case decides whether the token in it
    is any good. It only refuses a request whose `Origin` is not this site.

    Raises:
        OriginNotAllowed: If the request names an origin that is not one of
            the configured ones.

    """
    origin = request.headers.get(ORIGIN_HEADER)
    if origin is None:
        return
    allowed: frozenset[str] = getattr(request.app.state, ALLOWED_ORIGINS_STATE_KEY, frozenset())
    if normalise_origin(origin) in allowed:
        return
    logger.warning(
        "auth.origin_refused",
        extra={
            "origin": origin[:LOGGED_ORIGIN_MAX_LENGTH],
            "path": request.url.path,
            "allowed_count": len(allowed),
        },
    )
    raise OriginNotAllowed(
        "Attempted to use the session cookie from an origin that is not this site.",
        {"reason": "origin-not-allowed"},
    )


declare_policy(refresh_cookie_access, REFRESH_COOKIE_POLICY)


def never_store(response: Response) -> None:
    """Forbid any cache from keeping a response that carries or changes a credential."""
    response.headers[CACHE_CONTROL_HEADER] = CACHE_CONTROL_NO_STORE_VALUE


def get_client_details(request: Request) -> ClientDetails:
    """Return where the request came from, as the server worked it out."""
    return ClientDetails(
        address=current_client_address(), user_agent=request.headers.get(USER_AGENT_HEADER)
    )


ClientDetailsDependency = Annotated[ClientDetails, Depends(get_client_details)]


def get_presented_refresh_token(request: Request) -> str | None:
    """Return the refresh token in the cookie of the request, or None."""
    return RefreshCookie.read_from(request)


PresentedRefreshToken = Annotated[str | None, Depends(get_presented_refresh_token)]


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


def require_fresh_roles(*allowed: UserRole) -> Callable[[UserAccount, Session], UserAccount]:
    """Build a dependency that reads the account again before admitting the listed roles.

    The row is read with a shared lock, which holds until the request ends its
    transaction. A change of role or a deactivation by somebody else waits for
    that, so it cannot land between this check and the action it guards.

    Args:
        allowed: The roles permitted to reach the endpoint. Never empty.

    """
    admit = require_roles(*allowed)

    def dependency(user: AuthenticatedUser, session: SessionDependency) -> UserAccount:
        """Read the account again, under a lock, and apply the same two checks."""
        statement = (
            select(UserAccount)
            .where(col(UserAccount.id) == user.id)
            .execution_options(populate_existing=True)
            .with_for_update(read=True)
        )
        fresh = session.exec(statement).first()
        if fresh is None:
            raise AuthenticationFailure(
                "Attempted to act as an account that no longer exists.",
                {"reason": "unknown-subject"},
            )
        record_actor_role(fresh.role.value)
        logger.debug("auth.account_read_again", extra={"user_id": str(fresh.id)})
        return admit(get_active_user(fresh))

    declare_policy(dependency, role_policy(frozenset(allowed)))
    return dependency


# The dependency of every route that waives a charge, manages users or roles,
# or forces the release of an allocation. None of them exists yet.
FreshAdminUser = Annotated[UserAccount, Depends(require_fresh_roles(UserRole.ADMIN))]


# ---------------------------------------------------------------------------
# The identity half of the composition root. Each function returns a port or a
# use case, and the body chooses the implementation behind it.
# ---------------------------------------------------------------------------


def get_throttle() -> Throttle:
    """Return the one throttle of the process. Its counters are in the database."""
    return _THROTTLE


def get_login_rules() -> LoginThrottleRules:
    """Return the two sign in rules, with the limits the process was configured with."""
    return _LOGIN_RULES


def get_password_verifier() -> PasswordVerifier:
    """Return the bcrypt password verifier."""
    return _PASSWORD_VERIFIER


def get_access_token_issuer() -> AccessTokenIssuer:
    """Return the issuer that signs access tokens with the key of the service."""
    return _ACCESS_TOKEN_ISSUER


AccessTokenIssuerDependency = Annotated[AccessTokenIssuer, Depends(get_access_token_issuer)]


def get_sign_in_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    passwords: Annotated[PasswordVerifier, Depends(get_password_verifier)],
    tokens: AccessTokenIssuerDependency,
    throttle: Annotated[Throttle, Depends(get_throttle)],
    rules: Annotated[LoginThrottleRules, Depends(get_login_rules)],
) -> SignInUseCase:
    """Return the sign in use case, wired to its collaborators and the configured limits."""
    return SignInUseCase(uow, clock, passwords, tokens, throttle, rules)


def get_refresh_session_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, tokens: AccessTokenIssuerDependency
) -> RefreshSessionUseCase:
    """Return the refresh use case, wired to its unit of work, clock and token issuer."""
    return RefreshSessionUseCase(uow, clock, tokens)


def get_sign_out_use_case(uow: UnitOfWorkDependency, clock: ClockDependency) -> SignOutUseCase:
    """Return the sign out use case, wired to its unit of work and clock."""
    return SignOutUseCase(uow, clock)


SignIn = Annotated[SignInUseCase, Depends(get_sign_in_use_case)]
RefreshSession = Annotated[RefreshSessionUseCase, Depends(get_refresh_session_use_case)]
SignOut = Annotated[SignOutUseCase, Depends(get_sign_out_use_case)]
