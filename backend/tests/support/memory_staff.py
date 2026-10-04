"""An in memory unit of work for the staff accounts and the customer holds.

The use cases of user and role management reach the accounts, the
administrators' lock, the refresh sessions, the branches, the customers and the
audit log through the unit of work, and read their answer back through the
`StaffDirectory` port once they have committed, whose double is in
`memory_staff_reads`. The customers are in `memory_staff_customers`.
Everything is kept here in plain dictionaries, and work is kept only when
`commit` is called, so a test can see that a refusal wrote nothing.

The store can be told what the database would do. `address_taken_at_write`
makes the next new account lose its address to the unique constraint after
the lookup found it free, `fail_audit` makes the audit write fail and
`forget_answers` makes the directory lose what was committed, which a real
commit never does. Nothing is locked, because the locks are proved against
PostgreSQL in tests/integration, but every ask for the administrators' lock is
counted so a test can see it was asked.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import TracebackType
from typing import Final, Self
from uuid import UUID, uuid4

from app.application.identity.customer_directory import CustomerSummary
from app.application.identity.ports import EmailAlreadyRegistered
from app.domain.account import Account
from app.domain.audit import AuditEvent
from app.domain.enums import AccountStatus, RevokeReason, UserRole
from app.domain.identity import Branch
from app.domain.session import RefreshSession
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory_outbox import StoreFault
from tests.support.memory_staff_customers import StandingCustomers, StandingDirectory
from tests.support.memory_staff_reads import MemoryStaffDirectory

COMMIT: Final[str] = "commit"
SESSION_LIFETIME: Final[timedelta] = timedelta(days=14)


@dataclass
class StaffRecords:
    """Everything a transaction of user and role management can change."""

    accounts: dict[UUID, Account] = field(default_factory=dict)
    sessions: dict[UUID, RefreshSession] = field(default_factory=dict)
    standings: dict[UUID, AccountStatus] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)


@dataclass
class StaffStore:
    """The committed accounts, the reference data and what the database would do.

    Attributes:
        committed: What has been committed so far.
        branches: The branches, by code.
        closed_branch_codes: The codes of branches that stopped trading.
        customers: The customers as the counter reads them, by profile key.
        journal: `commit` for every commit, in order.
        address_taken_at_write: True to make the next new account lose its address.
        fail_audit: When True, recording an audit event raises.
        forget_answers: When True, the directory finds nothing.
        locks_asked: How many times the administrators were locked.

    """

    committed: StaffRecords = field(default_factory=StaffRecords)
    branches: dict[str, Branch] = field(default_factory=dict)
    closed_branch_codes: set[str] = field(default_factory=set)
    customers: dict[UUID, CustomerSummary] = field(default_factory=dict)
    journal: list[str] = field(default_factory=list)
    address_taken_at_write: bool = False
    fail_audit: bool = False
    forget_answers: bool = False
    locks_asked: int = 0

    def keep(
        self,
        *,
        role: UserRole,
        branch_code: str | None = None,
        email: str | None = None,
        is_active: bool = True,
        full_name: str = "Wesley Adonis",
    ) -> Account:
        """Commit an account a test starts from and return it."""
        branch_id = self.branches[branch_code].id if branch_code is not None else None
        account = Account(
            id=uuid4(),
            email=email or f"person.{uuid4().hex[:8]}@toolshedhire.co.za",
            password_hash="stand-in-hash-of:a-password-somebody-chose",
            role=role,
            full_name=full_name,
            branch_id=branch_id,
            is_active=is_active,
        )
        self.committed.accounts[account.id] = account
        return account

    def open_session(self, account: Account) -> RefreshSession:
        """Commit a live refresh session of an account and return it."""
        session = RefreshSession(
            user_account_id=account.id,
            family_id=uuid4(),
            token_hash=uuid4().hex,
            issued_at=DEFAULT_INSTANT,
            expires_at=DEFAULT_INSTANT + SESSION_LIFETIME,
        )
        self.committed.sessions[session.id] = session
        return session

    def account(self, account_id: UUID) -> Account:
        """Return the committed state of an account."""
        return self.committed.accounts[account_id]

    def standing_of(self, customer_profile_id: UUID) -> AccountStatus:
        """Return the committed standing of a customer."""
        stored = self.customers[customer_profile_id].account_status
        return self.committed.standings.get(customer_profile_id, stored)

    @property
    def events(self) -> list[AuditEvent]:
        """Return the audit events committed so far."""
        return self.committed.audit_events


class _Accounts:
    """The account repository over the working copy."""

    def __init__(self, store: StaffStore, working: StaffRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def find_by_email_for_update(self, email: str) -> Account | None:
        """Return a copy of the account with this address, if there is one."""
        for account in self._working.accounts.values():
            if account.email.lower() == email.lower():
                return copy.deepcopy(account)
        return None

    def get_for_update(self, account_id: UUID) -> Account | None:
        """Return a copy of the account with this key. Nothing is locked in memory."""
        return copy.deepcopy(self._working.accounts.get(account_id))

    def add(self, account: Account) -> None:
        """Keep a new account, or fail as a lost race for its address does."""
        if self._store.address_taken_at_write:
            self._store.address_taken_at_write = False
            raise EmailAlreadyRegistered
        self._working.accounts[account.id] = copy.deepcopy(account)

    def save_security_state(self, account: Account) -> None:
        """Keep the password hash, the verification, the two tokens and the lockout."""
        stored = self._working.accounts[account.id]
        stored.password_hash = account.password_hash
        stored.email_verification = account.email_verification
        stored.password_reset = account.password_reset


class _Staff:
    """The staff repository over the working copy."""

    def __init__(self, store: StaffStore, working: StaffRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def lock_active_administrators(self) -> frozenset[UUID]:
        """Return every active administrator, and count the ask."""
        self._store.locks_asked += 1
        return frozenset(
            account.id
            for account in self._working.accounts.values()
            if account.role is UserRole.ADMIN and account.is_active
        )

    def save_staff(self, account: Account) -> None:
        """Keep the name, the phone, the role, the branch and whether the account is active."""
        self._working.accounts[account.id] = copy.deepcopy(account)


class _Sessions:
    """The part of the session repository a deactivation writes through."""

    def __init__(self, working: StaffRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

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


class StaffBranches:
    """The branch repository."""

    def __init__(self, store: StaffStore) -> None:
        """Bind to the store that holds the branches."""
        self._store = store

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the trading branch with this code, if there is one."""
        if code in self._store.closed_branch_codes:
            return None
        return self._store.branches.get(code)

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key, trading or not."""
        return next((b for b in self._store.branches.values() if b.id == branch_id), None)


class _AuditLog:
    """The audit log over the working copy."""

    def __init__(self, store: StaffStore, working: StaffRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def record(self, event: AuditEvent) -> None:
        """Keep the event, or fail when the test has switched the fault on."""
        if self._store.fail_audit:
            raise StoreFault("The audit event could not be written.")
        self._working.audit_events.append(event)


class MemoryStaffUnitOfWork:
    """A unit of work over the in memory accounts and customers."""

    accounts: _Accounts
    staff: _Staff
    sessions: _Sessions
    branches: StaffBranches
    customers: StandingCustomers
    customer_directory: StandingDirectory
    audit: _AuditLog

    def __init__(self, store: StaffStore) -> None:
        """Bind the unit of work to the store it commits into."""
        self.store = store
        self._working: StaffRecords | None = None

    def __enter__(self) -> Self:
        """Take a working copy of what is committed."""
        working = copy.deepcopy(self.store.committed)
        self._working = working
        self.accounts = _Accounts(self.store, working)
        self.staff = _Staff(self.store, working)
        self.sessions = _Sessions(working)
        self.branches = StaffBranches(self.store)
        self.customers = StandingCustomers(self.store, working)
        self.customer_directory = StandingDirectory(self.store, working)
        self.audit = _AuditLog(self.store, working)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Throw the working copy away. Anything committed has already been kept."""
        self._working = None

    def commit(self) -> None:
        """Make the working copy what is committed."""
        if self._working is None:
            raise RuntimeError("Attempted to commit a staff unit of work that is not open.")
        self.store.committed = copy.deepcopy(self._working)
        self.store.journal.append(COMMIT)


__all__ = [
    "COMMIT",
    "MemoryStaffDirectory",
    "MemoryStaffUnitOfWork",
    "StaffStore",
    "StoreFault",
]
