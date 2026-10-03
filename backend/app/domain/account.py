"""The sign in account, its lockout and its two single use tokens (BR-45 to BR-47).

An account is who somebody is when they sign in. It carries one role, an
optional branch, the facts the lockout rule works with and the two tokens that
prove an email address and reset a password.

Five failed sign ins inside fifteen minutes lock the account for fifteen
minutes (BR-46). The account does not remember when each failure happened, so
whoever records a failure tells it how many failures the last fifteen minutes
hold, this one included. The account keeps the smaller of that number and its
own count plus one. Its own count goes back to zero on a success, on a reset
and when a lock has run out, so a failure from before any of those is never
counted again, even while the fifteen minutes it belongs to are still running.

A token is redeemed here and nowhere else. Redeeming one clears it, which is
what makes it single use, and a token that is unknown, used or out of time is
refused in the same way.

Nothing here knows how a password is hashed or how an account is stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

from app.domain.account_tokens import PendingToken
from app.domain.enums import UserRole
from app.domain.identity import Actor

# The failure that locks the account, and the span the failures are counted
# over (BR-46).
MAXIMUM_FAILED_LOGINS: Final[int] = 5
FAILED_LOGIN_WINDOW: Final[timedelta] = timedelta(minutes=15)
LOCKOUT_DURATION: Final[timedelta] = timedelta(minutes=15)
# A failure is always inside its own window, so the window never holds fewer.
SMALLEST_FAILURE_COUNT: Final[int] = 1


@dataclass(slots=True)
class Account:
    """A sign in account, as far as signing in and account security need to know it.

    Attributes:
        id: The account key.
        email: The address the holder signs in with, in lower case.
        password_hash: The stored hash. Never logged and never returned.
        role: The single role the account holds.
        full_name: The name of the holder.
        phone: The number of the holder, when one was given.
        branch_id: The branch of a counter account, and None for anyone else.
        is_active: False once an administrator has deactivated the account.
        email_verified_at: When the holder proved the address, or None.
        failed_login_count: How many sign ins failed inside the window, as of
            the last failure and since the count was last cleared.
        locked_until: The instant a lock ends, or None when there is no lock.
        last_login_at: When the holder last signed in.
        email_verification: The pending verification token, or None.
        password_reset: The pending reset token, or None.

    """

    id: UUID
    email: str
    password_hash: str = field(repr=False)
    role: UserRole
    full_name: str
    phone: str | None = None
    branch_id: UUID | None = None
    is_active: bool = True
    email_verified_at: datetime | None = None
    failed_login_count: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    email_verification: PendingToken | None = None
    password_reset: PendingToken | None = None

    @classmethod
    def registered_customer(
        cls, *, email: str, password_hash: str, full_name: str, phone: str
    ) -> Account:
        """Return the account of somebody who has just registered.

        It is a customer, it is active and its address is not verified yet.
        """
        return cls(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            role=UserRole.CUSTOMER,
            full_name=full_name,
            phone=phone,
        )

    @property
    def email_verified(self) -> bool:
        """Return True when the holder has proved the address."""
        return self.email_verified_at is not None

    def is_locked(self, now: datetime) -> bool:
        """Return True while a lock is still running at `now`."""
        return self.locked_until is not None and now < self.locked_until

    def record_failed_login(self, now: datetime, *, failures_in_window: int) -> bool:
        """Count one failed sign in, and lock the account when it is the fifth in the window.

        A lock that has already run out is cleared first, so the count starts
        again from this failure.

        Args:
            now: The instant of the failure, from the clock.
            failures_in_window: How many sign ins of this account failed in
                the fifteen minutes that end at `now`, this one included.

        Returns:
            True when this failure locked the account.

        """
        if self.locked_until is not None and now >= self.locked_until:
            self.clear_lockout()
        in_window = max(failures_in_window, SMALLEST_FAILURE_COUNT)
        self.failed_login_count = min(self.failed_login_count + 1, in_window)
        if self.failed_login_count < MAXIMUM_FAILED_LOGINS:
            return False
        self.locked_until = now + LOCKOUT_DURATION
        return True

    def record_successful_login(self, now: datetime) -> None:
        """Clear the failure count and any lock, and note the sign in."""
        self.clear_lockout()
        self.last_login_at = now

    def clear_lockout(self) -> None:
        """Forget every failure counted so far and lift any lock."""
        self.failed_login_count = 0
        self.locked_until = None

    def start_email_verification(self, pending: PendingToken) -> None:
        """Keep a new verification token, in place of any earlier one."""
        self.email_verification = pending

    def verify_email(self, presented_token: str, now: datetime) -> bool:
        """Redeem a verification token and mark the address as proved.

        Returns:
            True when the token was the pending one and still in time. The
            token is cleared, so it cannot be redeemed again. False otherwise,
            and nothing is changed.

        """
        pending = self.email_verification
        if pending is None or not pending.accepts(presented_token, now):
            return False
        self.email_verification = None
        if self.email_verified_at is None:
            self.email_verified_at = now
        return True

    def start_password_reset(self, pending: PendingToken) -> None:
        """Keep a new reset token, in place of any earlier one."""
        self.password_reset = pending

    def reset_password(self, presented_token: str, new_password_hash: str, now: datetime) -> bool:
        """Redeem a reset token, take the new hash and lift any lock.

        Returns:
            True when the token was the pending one and still in time. The
            token is cleared, so it cannot be redeemed again. False otherwise,
            and nothing is changed.

        """
        pending = self.password_reset
        if pending is None or not pending.accepts(presented_token, now):
            return False
        self.password_reset = None
        self.password_hash = new_password_hash
        self.clear_lockout()
        return True

    def as_actor(self) -> Actor:
        """Return the account as the actor of an operation, with its role and branch."""
        return Actor(user_id=self.id, role=self.role, branch_id=self.branch_id)
