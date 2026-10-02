"""The sign in account, and the rule that locks it after repeated failures (BR-46).

An account is who somebody is when they sign in. It carries one role, an
optional branch and the three facts the lockout rule works with, which are how
many sign ins have failed, until when the account is locked and when it last
signed in.

The lockout counts failures in a row. A fifth failure locks the account for
fifteen minutes. A success sets the count back to zero, and so does the first
failure after a lock has run out. The design document words the rule as five
failures inside fifteen minutes. The two columns it gives the rule hold no
time for the first failure, so I count every failure since the last success
instead. That locks an account in every case the document describes and in a
few it does not, which is the safe side to be wrong on.

Nothing here knows how a password is hashed or how an account is stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from app.domain.enums import UserRole
from app.domain.identity import Actor

# The failure that locks the account (BR-46).
MAXIMUM_FAILED_LOGINS: Final[int] = 5
LOCKOUT_DURATION: Final[timedelta] = timedelta(minutes=15)


@dataclass(slots=True)
class Account:
    """A sign in account, as far as signing in needs to know it.

    Attributes:
        id: The account key.
        email: The address the holder signs in with, in lower case.
        password_hash: The stored hash. Never logged and never returned.
        role: The single role the account holds.
        full_name: The name of the holder.
        branch_id: The branch of a counter account, and None for anyone else.
        is_active: False once an administrator has deactivated the account.
        email_verified_at: When the holder proved the address, or None.
        failed_login_count: How many sign ins have failed since the last
            success.
        locked_until: The instant a lock ends, or None when there is no lock.
        last_login_at: When the holder last signed in.

    """

    id: UUID
    email: str
    password_hash: str = field(repr=False)
    role: UserRole
    full_name: str
    branch_id: UUID | None = None
    is_active: bool = True
    email_verified_at: datetime | None = None
    failed_login_count: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def email_verified(self) -> bool:
        """Return True when the holder has proved the address."""
        return self.email_verified_at is not None

    def is_locked(self, now: datetime) -> bool:
        """Return True while a lock is still running at `now`."""
        return self.locked_until is not None and now < self.locked_until

    def record_failed_login(self, now: datetime) -> bool:
        """Count one failed sign in, and lock the account when it is the fifth.

        A lock that has already run out is cleared first, so the count starts
        again from this failure.

        Args:
            now: The instant of the failure, from the clock.

        Returns:
            True when this failure locked the account.

        """
        if self.locked_until is not None and now >= self.locked_until:
            self.locked_until = None
            self.failed_login_count = 0
        self.failed_login_count += 1
        if self.failed_login_count < MAXIMUM_FAILED_LOGINS:
            return False
        self.locked_until = now + LOCKOUT_DURATION
        return True

    def record_successful_login(self, now: datetime) -> None:
        """Clear the failure count and any lock, and note the sign in."""
        self.failed_login_count = 0
        self.locked_until = None
        self.last_login_at = now

    def as_actor(self) -> Actor:
        """Return the account as the actor of an operation, with its role and branch."""
        return Actor(user_id=self.id, role=self.role, branch_id=self.branch_id)
