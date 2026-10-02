"""An in memory unit of work for the identity use cases, and the two fakes they take.

`IdentityMemoryUnitOfWork` extends the in memory unit of work in `memory` with
the things signing in and the account use cases need, which are accounts,
refresh sessions, throttle counters and the details of a customer. It keeps
them the same way. Work is only kept when `commit` is called and is thrown
away when the block is left without one, which is what lets a test prove that
a refused sign in still saves its failure count.

The fakes that stand in for the cryptography are in `memory_crypto` and are
exported from here as well, because the session tests have always found them
here. The repository of a customer's own details is in `memory_customers`.

None of this makes any attempt at locking. The row locks are proved against
PostgreSQL in tests/integration.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Self
from uuid import UUID, uuid4

from app.application.identity.ports import EmailAlreadyRegistered
from app.domain.account import Account
from app.domain.customer_account import CustomerDetails
from app.domain.enums import RevokeReason, UserRole
from app.domain.session import RefreshSession
from tests.support.memory import InMemoryUnitOfWork, MemoryStore
from tests.support.memory_crypto import (
    FAKE_ACCESS_LIFETIME_SECONDS,
    CountingPasswordVerifier,
    FakeAccessTokenIssuer,
    fake_hash,
)
from tests.support.memory_customers import AccountCustomers

KNOWN_PASSWORD: Final[str] = "correct-horse-battery-staple"
KNOWN_EMAIL: Final[str] = "nomsa.dlamini@example.co.za"


@dataclass
class IdentityRecords:
    """Everything a session transaction can change."""

    accounts: dict[UUID, Account] = field(default_factory=dict)
    sessions: dict[UUID, RefreshSession] = field(default_factory=dict)
    counters: dict[tuple[str, datetime], int] = field(default_factory=dict)
    details: dict[UUID, CustomerDetails] = field(default_factory=dict)


@dataclass
class IdentityStore:
    """The committed accounts, sessions, counters and customer details.

    Attributes:
        committed: What has been committed so far.
        address_taken_at_write: When True, writing a new account fails the way
            it does when another registration took the address a moment before.

    """

    committed: IdentityRecords = field(default_factory=IdentityRecords)
    address_taken_at_write: bool = False

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

    def __init__(self, identity: IdentityStore, working: IdentityRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._identity = identity
        self._working = working

    def find_by_email_for_update(self, email: str) -> Account | None:
        """Return a copy of the account with this address, if there is one."""
        for account in self._working.accounts.values():
            if account.email.lower() == email.lower():
                return copy.deepcopy(account)
        return None

    def find_by_email_verification_hash_for_update(self, token_hash: str) -> Account | None:
        """Return a copy of the account holding this verification token hash, if any."""
        for account in self._working.accounts.values():
            pending = account.email_verification
            if pending is not None and pending.token_hash == token_hash:
                return copy.deepcopy(account)
        return None

    def find_by_password_reset_hash_for_update(self, token_hash: str) -> Account | None:
        """Return a copy of the account holding this reset token hash, if any."""
        for account in self._working.accounts.values():
            pending = account.password_reset
            if pending is not None and pending.token_hash == token_hash:
                return copy.deepcopy(account)
        return None

    def get(self, account_id: UUID) -> Account | None:
        """Return a copy of the account with this key, if there is one."""
        return copy.deepcopy(self._working.accounts.get(account_id))

    def get_for_update(self, account_id: UUID) -> Account | None:
        """Return a copy of the account with this key, if there is one."""
        return self.get(account_id)

    def add(self, account: Account) -> None:
        """Keep a copy of a new account, or fail as a lost race for its address does."""
        if self._identity.address_taken_at_write:
            raise EmailAlreadyRegistered
        self._working.accounts[account.id] = copy.deepcopy(account)

    def save_security_state(self, account: Account) -> None:
        """Keep the password hash, the verification, the two tokens and the lockout."""
        stored = self._working.accounts[account.id]
        stored.password_hash = account.password_hash
        stored.email_verified_at = account.email_verified_at
        stored.email_verification = account.email_verification
        stored.password_reset = account.password_reset
        stored.failed_login_count = account.failed_login_count
        stored.locked_until = account.locked_until

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

    def revoke_all_for_account(
        self, *, user_account_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Revoke every live session of an account and return how many there were."""
        live = [
            session
            for session in self._working.sessions.values()
            if session.user_account_id == user_account_id and session.revoked_at is None
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

    def total_since(self, bucket_key_hash: str, since: datetime) -> int:
        """Return the sum of the counters of a bucket whose windows began at or after `since`."""
        return sum(
            count
            for (bucket, window_started_at), count in self._working.counters.items()
            if bucket == bucket_key_hash and window_started_at >= since
        )


class IdentityMemoryUnitOfWork(InMemoryUnitOfWork):
    """The in memory unit of work, with accounts, sessions, counters and details as well."""

    accounts: _Accounts
    sessions: _Sessions
    rate_limits: _RateLimits
    customers: AccountCustomers

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
        """Point the identity repositories at one working copy."""
        working = copy.deepcopy(self.identity.committed)
        self._identity_working = working
        self.accounts = _Accounts(self.identity, working)
        self.sessions = _Sessions(working)
        self.rate_limits = _RateLimits(working)
        self.customers = AccountCustomers(self.store, self.working_records(), working)


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
