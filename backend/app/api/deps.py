"""The layered authorisation dependency chain.

Four layers, each building on the one before it.

1. `get_bearer_token` pulls the credential out of the Authorization header.
2. `get_authenticated_user` verifies the token and loads the account.
3. `get_active_user` refuses a deactivated account.
4. `require_roles` refuses an account whose role is not in the allowed set.

The token carries the role and the branch as claims, and this chain does not
rely on them. It reads the role from the database row on every request, so an
access token minted before a demotion stops granting the old permissions the
moment the row changes and not fifteen minutes later. An action that must not
run on a stale row even within one request uses `require_fresh_roles` from
`app/api/identity_deps.py`.

Every endpoint must depend on one of the role dependencies, or on
`public_access` when it admits a caller with no account (BR-41). Each of them
is registered as a policy in `app/api/access_policy.py`, and the application
refuses to start while any route depends on none of them.

The second layer also records the role of the account it loaded against the
current request. The access log reads it from there, which is how one line per
request can say who made it without the middleware querying the database.

This module is also the composition root. The application layer depends on
ports and imports nothing from the infrastructure layer, so something has to
choose the implementations, and that happens in the dependencies at the foot of
this file. A use case reaches a router already holding the SQL unit of work,
the system clock and the email gateway, and the router never learns which
classes those are. The booking use cases are wired from these parts in
`app/api/booking_deps.py`, and the query objects of the public read side in
`app/api/catalogue_deps.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.api.access_policy import PUBLIC_POLICY, declare_policy, role_policy
from app.application.clock import Clock
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.ports import NotificationGateway
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import UserRole
from app.domain.errors import AuthenticationFailure, AuthorisationFailure, InactiveAccount
from app.infrastructure.clock import SystemClock
from app.infrastructure.database import get_session
from app.infrastructure.models import UserAccount
from app.infrastructure.security import read_access_claims
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.request_context import record_actor_role

logger = logging.getLogger(__name__)

AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
# The attribute of the application state that holds the email gateway. The
# application factory sets it once, when the application is built.
NOTIFICATION_GATEWAY_STATE_KEY = "notification_gateway"

_SYSTEM_CLOCK = SystemClock()

SessionDependency = Annotated[Session, Depends(get_session)]


def get_clock() -> Clock:
    """Return the system clock. A test overrides this to hold the time still."""
    return _SYSTEM_CLOCK


ClockDependency = Annotated[Clock, Depends(get_clock)]


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


def get_authenticated_user(
    token: TokenDependency, session: SessionDependency, clock: ClockDependency
) -> UserAccount:
    """Verify the token and load the account it identifies.

    Raises:
        AuthenticationFailure: If the token fails verification, or if it names
            an account that no longer exists. The two cases are deliberately
            answered identically, so a caller cannot probe for valid ids.

    """
    user_id = read_access_claims(token, now=clock.now()).subject
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
    record_actor_role(account.role.value)
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

    declare_policy(dependency, role_policy(permitted))
    return dependency


CustomerUser = Annotated[UserAccount, Depends(require_roles(UserRole.CUSTOMER))]
CounterUser = Annotated[UserAccount, Depends(require_roles(UserRole.COUNTER_STAFF, UserRole.ADMIN))]
AdminUser = Annotated[UserAccount, Depends(require_roles(UserRole.ADMIN))]
AnyRoleUser = Annotated[
    UserAccount,
    Depends(require_roles(UserRole.CUSTOMER, UserRole.COUNTER_STAFF, UserRole.ADMIN)),
]


def public_access() -> None:
    """Declare that an endpoint admits a caller with no account.

    It checks nothing, because there is nothing to check. It exists so that a
    public endpoint states its policy in its route, the same way a protected
    one names its roles, and is never public merely because nobody declared
    anything (BR-41).
    """


declare_policy(public_access, PUBLIC_POLICY)


# ---------------------------------------------------------------------------
# The composition root. Each function returns a port, and the body chooses the
# implementation behind it.
# ---------------------------------------------------------------------------


def get_unit_of_work(session: SessionDependency) -> UnitOfWork:
    """Return a SQL unit of work over the request scoped session.

    The session is borrowed and not owned. The authentication dependency reads
    the account through the same one, and the request closes it, so the unit of
    work is told not to.
    """
    return SqlAlchemyUnitOfWork(lambda: session, close_on_exit=False)


UnitOfWorkDependency = Annotated[UnitOfWork, Depends(get_unit_of_work)]


def get_notification_gateway(request: Request) -> NotificationGateway:
    """Return the email gateway the application was built with.

    Raises:
        RuntimeError: If the application carries no gateway. The application
            factory installs one, so this means an application was assembled
            some other way and then asked to send email.

    """
    gateway = getattr(request.app.state, NOTIFICATION_GATEWAY_STATE_KEY, None)
    if not isinstance(gateway, NotificationGateway):
        raise RuntimeError(
            "Attempted to send a notification from an application that was built without "
            f"an email gateway. Set `app.state.{NOTIFICATION_GATEWAY_STATE_KEY}` when the "
            "application is assembled, as `create_app` does."
        )
    return gateway


NotificationGatewayDependency = Annotated[NotificationGateway, Depends(get_notification_gateway)]


def get_notification_dispatcher(
    uow: UnitOfWorkDependency, gateway: NotificationGatewayDependency, clock: ClockDependency
) -> NotificationDispatcher:
    """Return the dispatcher that sends queued notifications after a commit."""
    return NotificationDispatcher(uow, gateway, clock)


NotificationDispatcherDependency = Annotated[
    NotificationDispatcher, Depends(get_notification_dispatcher)
]
