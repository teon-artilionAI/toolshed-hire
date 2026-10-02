"""The three session endpoints, which are sign in, refresh and sign out.

`POST /api/auth/login` is public by declaration, because a caller cannot
present a token before they have one. It answers a wrong password, an unknown
address, a locked account and a deactivated account with the same 401, and it
answers a caller who has tried too often with a 429 and a `Retry-After`.

`POST /api/auth/refresh` and `POST /api/auth/logout` take no body. They are
authenticated by the refresh cookie alone, so both check the `Origin` of the
request before anything else.

The access token is returned in the response body and never set as a cookie.
The refresh token is set as a cookie and never returned in a body. A refresh
that is refused clears the cookie on its way out, which the error handler sees
to, so a browser does not keep presenting a token that no longer works.

The routers do no work of their own beyond the HTTP boundary. Each hands a
command to a use case that arrives already wired, and shapes what comes back.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import public_access
from app.api.identity_deps import (
    ClientDetailsDependency,
    PresentedRefreshToken,
    RefreshCookieDependency,
    RefreshSession,
    SignIn,
    SignOut,
    never_store,
    refresh_cookie_access,
)
from app.api.schemas import LoginRequest, TokenResponse, UserResponse, wire_role
from app.application.identity.refresh_session import RefreshSessionCommand
from app.application.identity.sessions import SessionGrant
from app.application.identity.sign_in import SignInCommand
from app.application.identity.sign_out import SignOutCommand

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(never_store)])

INVALID_CREDENTIALS_RESPONSE: dict[str, str] = {
    "description": "The sign in was refused. The body is the same whatever the reason."
}
TOO_MANY_ATTEMPTS_RESPONSE: dict[str, str] = {
    "description": "Too many attempts. `Retry-After` carries the wait in seconds."
}
SESSION_EXPIRED_RESPONSE: dict[str, str] = {
    "description": "The refresh cookie is missing, unknown, expired, revoked or already used."
}
ORIGIN_REFUSED_RESPONSE: dict[str, str] = {
    "description": "The request named an origin that is not one of the configured ones."
}


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange credentials for an access token and a refresh cookie",
    dependencies=[Depends(public_access)],
    responses={
        status.HTTP_401_UNAUTHORIZED: INVALID_CREDENTIALS_RESPONSE,
        status.HTTP_429_TOO_MANY_REQUESTS: TOO_MANY_ATTEMPTS_RESPONSE,
    },
)
def post_login(
    payload: LoginRequest,
    response: Response,
    use_case: SignIn,
    client: ClientDetailsDependency,
    cookie: RefreshCookieDependency,
) -> TokenResponse:
    """Verify credentials, open a session and issue both tokens.

    Raises:
        InvalidCredentials: If the sign in was refused. Mapped to HTTP 401.
        TooManyAttempts: If the caller is throttled. Mapped to HTTP 429.

    """
    grant = use_case.execute(
        SignInCommand(email=payload.email, password=payload.password, client=client)
    )
    cookie.set_on(response, grant.refresh_token, grant.refresh_max_age_seconds)
    return _token_response(grant)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange the refresh cookie for a new access token and a new cookie",
    dependencies=[Depends(refresh_cookie_access)],
    responses={
        status.HTTP_401_UNAUTHORIZED: SESSION_EXPIRED_RESPONSE,
        status.HTTP_403_FORBIDDEN: ORIGIN_REFUSED_RESPONSE,
    },
)
def post_refresh(
    response: Response,
    use_case: RefreshSession,
    presented_token: PresentedRefreshToken,
    client: ClientDetailsDependency,
    cookie: RefreshCookieDependency,
) -> TokenResponse:
    """Rotate the refresh token and issue a new access token.

    Raises:
        SessionExpired: If the cookie is missing or no longer good. Mapped to
            HTTP 401, with the cookie cleared.

    """
    grant = use_case.execute(
        RefreshSessionCommand(presented_token=presented_token, client=client)
    )
    cookie.set_on(response, grant.refresh_token, grant.refresh_max_age_seconds)
    return _token_response(grant)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the session of the refresh cookie and clear the cookie",
    dependencies=[Depends(refresh_cookie_access)],
    responses={status.HTTP_403_FORBIDDEN: ORIGIN_REFUSED_RESPONSE},
)
def post_logout(
    response: Response,
    use_case: SignOut,
    presented_token: PresentedRefreshToken,
    cookie: RefreshCookieDependency,
) -> None:
    """Revoke the session the cookie names, if any, and clear the cookie.

    The answer is 204 whether or not there was a cookie and whether or not it
    named a live session.
    """
    use_case.execute(SignOutCommand(presented_token=presented_token))
    cookie.clear_on(response)


def _token_response(grant: SessionGrant) -> TokenResponse:
    """Shape a session grant as the body of a sign in or a refresh."""
    account = grant.account
    return TokenResponse(
        access_token=grant.access_token,
        expires_in=grant.expires_in,
        user=UserResponse(
            id=account.id,
            email=account.email,
            full_name=account.full_name,
            role=wire_role(account.role),
            branch_code=account.branch_code,
            email_verified=account.email_verified,
        ),
    )
