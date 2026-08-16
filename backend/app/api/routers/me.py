"""The protected identity endpoint.

This is the endpoint the React client calls immediately after sign in, and it
is the one that proves the whole chain: a bearer token from the browser, a
verified signature, an account loaded from PostgreSQL, an active check and a
role check, and a body shaped like the frontend UserAccount type.

The role in the response is read from the database row, not from the token.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status

from app.api.deps import AnyRoleUser, SessionDependency, branch_code_of
from app.api.schemas import UserResponse, wire_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Return the signed in account",
)
def read_me(user: AnyRoleUser, session: SessionDependency) -> UserResponse:
    """Return the account behind the presented access token.

    Args:
        user: The active account, resolved by the layered auth dependencies.
        session: The request scoped session, used to resolve the branch code.

    Returns:
        The account in the shape the frontend UserAccount type expects.

    """
    logger.info(
        "identity.me_read",
        extra={"user_id": str(user.id), "role": user.role.value},
    )
    return UserResponse(
        id=user.id,
        name=user.full_name,
        email=user.email,
        role=wire_role(user.role),
        branch_code=branch_code_of(session, user),
        active=user.is_active,
    )
