"""Sign in endpoint.

Public by declaration, because a caller cannot present a token before they have
one. Everything else about it is deliberately conservative.

A wrong email and a wrong password return the same message, so the endpoint
cannot be used to enumerate which addresses hold accounts. The password
comparison runs even when no account was found, so the response time does not
disclose the answer either.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlmodel import select

from app.api.deps import SessionDependency, branch_code_of
from app.api.schemas import SignInRequest, TokenResponse, UserResponse, wire_role
from app.domain.errors import AuthenticationFailure, InactiveAccount
from app.infrastructure.models import UserAccount
from app.infrastructure.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# A bcrypt hash of an unusable password, compared against when no account
# matched so that the failure path costs the same as the success path.
_TIMING_EQUALISER_HASH = hash_password("not-a-real-password-timing-equaliser")
INVALID_CREDENTIALS_MESSAGE = (
    "Sign in failed. The email address or the password is wrong. "
    "No further detail is given deliberately."
)


@router.post(
    "/sign-in",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange credentials for an access token",
)
def post_sign_in(payload: SignInRequest, session: SessionDependency) -> TokenResponse:
    """Verify credentials and issue an access token.

    Args:
        payload: The email address and password as typed.
        session: The request scoped database session.

    Returns:
        The access token, its lifetime and the account it belongs to.

    Raises:
        AuthenticationFailure: If no account matches or the password is wrong.
        InactiveAccount: If the credentials are right but the account is
            deactivated. Reported separately from a wrong password because the
            holder needs to know to contact an administrator.

    """
    email = payload.email.strip().lower()
    logger.info("auth.sign_in_started", extra={"email": email})

    statement = select(UserAccount).where(UserAccount.email == email)
    account = session.exec(statement).first()

    stored_hash = account.password_hash if account else _TIMING_EQUALISER_HASH
    password_matches = verify_password(payload.password, stored_hash)

    if account is None or not password_matches:
        logger.warning(
            "auth.sign_in_rejected",
            extra={
                "email": email,
                "reason": "unknown-account" if account is None else "bad-password",
            },
        )
        raise AuthenticationFailure(INVALID_CREDENTIALS_MESSAGE, {"reason": "invalid-credentials"})

    if not account.is_active:
        logger.warning(
            "auth.sign_in_rejected_inactive",
            extra={"email": email, "user_id": str(account.id)},
        )
        raise InactiveAccount(
            f"Account {email} is deactivated and cannot sign in. "
            "An administrator can reactivate it.",
            {"reason": "account-deactivated"},
        )

    token, expires_in = create_access_token(account.id)
    account.last_login_at = datetime.now(UTC)
    session.add(account)
    session.commit()
    session.refresh(account)

    logger.info(
        "auth.sign_in_succeeded",
        extra={"user_id": str(account.id), "role": account.role.value, "expires_in": expires_in},
    )
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse(
            id=account.id,
            name=account.full_name,
            email=account.email,
            role=wire_role(account.role),
            branch_code=branch_code_of(session, account),
            active=account.is_active,
        ),
    )
