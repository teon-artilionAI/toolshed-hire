"""An in memory unit of work for the session use cases, and the two fakes they take.

`IdentityMemoryUnitOfWork` extends the in memory unit of work in `memory` with
the three things signing in needs, which are accounts, refresh sessions and
throttle counters. It keeps them the same way. Work is only kept when `commit`
is called and is thrown away when the block is left without one, which is what
lets a test prove that a refused sign in still saves its failure count.

The two fakes stand in for the cryptography. `CountingPasswordVerifier`
compares against a readable stand in for a hash and remembers every call, so a
test can assert that each path verified exactly once. `FakeAccessTokenIssuer`
hands back a value that is plainly not a token.

None of this makes any attempt at locking. The row locks are proved against
PostgreSQL in tests/integration.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Self
from uuid import UUID, uuid4

from app.application.identity.ports import IssuedAccessToken
from app.domain.account import Account
from app.domain.enums import RevokeReason, UserRole
from app.domain.session import RefreshSession
from tests.support.memory import InMemoryUnitOfWork, MemoryStore

FAKE_HASH_PREFIX: Final[str] = "stand-in-hash-of:"
FAKE_ACCESS_LIFETIME_SECONDS: Final[int] = 900
KNOWN_PASSWORD: Final[str] = "correct-horse-battery-staple"
KNOWN_EMAIL: Final[str] = "nomsa.dlamini@example.co.za"


def fake_hash(plain_password: str) -> str:
    """Return the readable stand in the counting verifier treats as a hash."""
    return f"{FAKE_HASH_PREFIX}{plain_password}"


@dataclass
class IdentityRecords:
    """Everything a session transaction can change."""

    accounts: dict[UUID, Account] = field(default_factory=dict)
    sessions: dict[UUID, RefreshSession] = field(default_factory=dict)
    counters: dict[tuple[str, datetime], int] = field(default_factory=dict)


@dataclass
class IdentityStore:
    """The committed accounts, sessions and counters."""

    committed: IdentityRecords = field(default_factory=IdentityRecords)

    def add_account(
        self,
        *,
        email: str = KNOWN_EMAIL,
        password: str = KNOWN_PASSWORD,
        role: UserRole = UserRole.CUSTOMER,
        branch_id: UUID | None = None,
        is_active: bool = True,
    ) -> Account:
        """Commit an account and return a copy of it."""
        account = Account(
            id=uuid4(),
            email=email,
            password_hash=fake_hash(password),
            role=role,
            full_name="Nomsa Dlamini",
            branch_id=branch_id,
            is_active=is_active,
        )
        self.committed.accounts[account.id] = account
        return copy.deepcopy(account)

    def account(self, account_id: UUID) -> Account:
        """Return the committed state of an account."""
        return self.committed.accounts[account_id]

    def family(self, family_id: UUID) -> list[RefreshSession]:
        """Return the committed sessions of a family, oldest first."""
        members = [s for s in self.committed.sessions.values() if s.family_id == family_id]
        return sorted(members, key=lambda member: member.issued_at)


class _Accounts:
    """The account repository over the working copy."""

    def __init__(self, working: IdentityRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def find_by_email_for_update(self, email: str) -> Account | None:
        """Return a copy of the account with this address, if there is one."""
        for account in self._working.accounts.values():
            if account.email.lower() == email.lower():
                return copy.deepcopy(account)
        return None

    def get(self, account_id: UUID) -> Account | None:
        """Return a copy of the account with this key, if there is one."""
        return copy.deepcopy(self._working.accounts.get(account_id))

    def save_login_state(self, account: Account) -> None:
        """Keep the failure count, the lock and the last sign in."""
        stored = self._working.accounts[account.id]
        stored.failed_login_count = account.failed_login_count
        stored.locked_until = account.locked_until
        stored.last_login_at = account.last_login_at


class _Sessions:
    """The refresh session repository over the working copy."""

    def __init__(self, working: IdentityRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def add(self, session: RefreshSession) -> None:
        """Keep a copy of a new session."""
        self._working.sessions[session.id] = copy.deepcopy(session)

    def find_by_token_hash_for_update(self, token_hash: str) -> RefreshSession | None:
        """Return a copy of the session a token hash names, if there is one."""
        for session in self._working.sessions.values():
            if session.token_hash == token_hash:
                return copy.deepcopy(session)
        return None

    def save_rotation(self, session: RefreshSession) -> None:
        """Keep that a session was used."""
        stored = self._working.sessions[session.id]
        stored.rotated_at = session.rotated_at
        stored.revoked_at = session.revoked_at
        stored.revoked_reason = session.revoked_reason

    def revoke_family(
        self, *, user_account_id: UUID, family_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Revoke every live session of a family and return how many there were."""
        live = [
            session
            for session in self._working.sessions.values()
            if session.family_id == family_id
            and session.user_account_id == user_account_id
            and session.revoked_at is None
        ]
        for session in live:
            session.revoked_at = at
            session.revoked_reason = reason
        return len(live)


class _RateLimits:
    """The throttle counters over the working copy."""

    def __init__(self, working: IdentityRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        """Add one to a counter and return the new count."""
        key = (bucket_key_hash, window_started_at)
        self._working.counters[key] = self._working.counters.get(key, 0) + 1
        return self._working.counters[key]

    def delete_windows_before(self, cutoff: datetime) -> int:
        """Delete every counter whose window began before the cutoff."""
        expired = [key for key in self._working.counters if key[1] < cutoff]
        for key in expired:
            del self._working.counters[key]
        return len(expired)


class IdentityMemoryUnitOfWork(InMemoryUnitOfWork):
    """The in memory unit of work, with accounts, sessions and counters as well."""

    accounts: _Accounts
    sessions: _Sessions
    rate_limits: _RateLimits

    def __init__(self, store: MemoryStore, identity: IdentityStore) -> None:
        """Bind the unit of work to the two stores it commits into."""
        super().__init__(store)
        self.identity = identity
        self._identity_working: IdentityRecords | None = None

    def __enter__(self) -> Self:
        """Take a working copy of both stores."""
        super().__enter__()
        self._bind_identity()
        return self

    def commit(self) -> None:
        """Make both working copies the committed state."""
        super().commit()
        if self._identity_working is not None:
            self.identity.committed = copy.deepcopy(self._identity_working)

    def rollback(self) -> None:
        """Replace both working copies with the committed state."""
        super().rollback()
        self._bind_identity()

    def _bind_identity(self) -> None:
        """Point the three identity repositories at one working copy."""
        working = copy.deepcopy(self.identity.committed)
        self._identity_working = working
        self.accounts = _Accounts(working)
        self.sessions = _Sessions(working)
        self.rate_limits = _RateLimits(working)


@dataclass
class CountingPasswordVerifier:
    """Compares against the stand in hash and remembers every call it was given.

    Attributes:
        calls: The stored hash handed to each call, in order. None is a call
            made for an account that could not be checked.

    """

    calls: list[str | None] = field(default_factory=list)

    def verify(self, plain_password: str, stored_hash: str | None) -> bool:
        """Record the call and answer whether the password matches the stand in."""
        self.calls.append(stored_hash)
        return stored_hash is not None and stored_hash == fake_hash(plain_password)


@dataclass
class FakeAccessTokenIssuer:
    """Issues a value that is plainly not a token, and remembers who it was for."""

    issued_for: list[UUID] = field(default_factory=list)

    def issue(self, account: Account, issued_at: datetime) -> IssuedAccessToken:
        """Return a made up access token for the account."""
        self.issued_for.append(account.id)
        return IssuedAccessToken(
            value=f"made-up-access-token-for-{account.role.value.lower()}",
            expires_in=FAKE_ACCESS_LIFETIME_SECONDS,
        )


__all__ = [
    "FAKE_ACCESS_LIFETIME_SECONDS",
    "KNOWN_EMAIL",
    "KNOWN_PASSWORD",
    "CountingPasswordVerifier",
    "FakeAccessTokenIssuer",
    "IdentityMemoryUnitOfWork",
    "IdentityRecords",
    "IdentityStore",
    "fake_hash",
]
