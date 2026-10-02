"""What signing in and refreshing both hand back, and how it is put together.

Both end the same way. A session row exists, the browser is owed a refresh
token and an access token, and the client wants to know who it is signed in
as. `grant_session` builds that answer inside the open unit of work, so the
two use cases cannot drift apart in what they return.

The two tokens are kept out of the representation of the grant. A grant that
found its way into a log line would otherwise carry both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.identity.ports import AccessTokenIssuer
from app.application.unit_of_work import UnitOfWork
from app.domain.account import Account
from app.domain.audit import ClientAddress
from app.domain.enums import UserRole
from app.domain.session import RefreshSession

# The entity type every authentication audit event is recorded against.
ACCOUNT_ENTITY_TYPE: Final[str] = "user_account"


@dataclass(frozen=True, slots=True)
class ClientDetails:
    """Where a request came from, as far as the server could tell.

    Attributes:
        address: The address the server derived for the client, or None.
        user_agent: What the client called itself, or None.

    """

    address: ClientAddress | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class SignedInAccount:
    """The account a session belongs to, as the client is told about it.

    Attributes:
        id: The account key.
        email: The address the holder signs in with.
        full_name: The name of the holder.
        role: The single role the account holds.
        branch_code: The code of the branch of a counter account, else None.
        email_verified: Whether the holder has proved the address.

    """

    id: UUID
    email: str
    full_name: str
    role: UserRole
    branch_code: str | None
    email_verified: bool


@dataclass(frozen=True, slots=True)
class SessionGrant:
    """Everything a client is owed once it is signed in.

    Attributes:
        access_token: The signed access token, for the response body.
        expires_in: The lifetime of the access token in seconds.
        refresh_token: The opaque refresh token, for the cookie and nowhere else.
        refresh_max_age_seconds: How long the cookie may be kept.
        account: Who is signed in.

    """

    access_token: str = field(repr=False)
    expires_in: int
    refresh_token: str = field(repr=False)
    refresh_max_age_seconds: int
    account: SignedInAccount


def grant_session(
    uow: UnitOfWork,
    tokens: AccessTokenIssuer,
    *,
    account: Account,
    session: RefreshSession,
    refresh_token: str,
    now: datetime,
) -> SessionGrant:
    """Build the grant for a session that has just been opened.

    Args:
        uow: The open unit of work, used to read the branch code.
        tokens: Signs the access token.
        account: The account that is signed in.
        session: The session that was just opened for it.
        refresh_token: The token whose hash the session holds.
        now: The current instant, from the clock.

    """
    issued = tokens.issue(account, now)
    return SessionGrant(
        access_token=issued.value,
        expires_in=issued.expires_in,
        refresh_token=refresh_token,
        refresh_max_age_seconds=session.seconds_left(now),
        account=SignedInAccount(
            id=account.id,
            email=account.email,
            full_name=account.full_name,
            role=account.role,
            branch_code=_branch_code_of(uow, account),
            email_verified=account.email_verified,
        ),
    )


def _branch_code_of(uow: UnitOfWork, account: Account) -> str | None:
    """Return the code of the branch a counter account is scoped to, or None."""
    if account.branch_id is None:
        return None
    branch = uow.branches.get(account.branch_id)
    return branch.code if branch is not None else None
