"""The ports of the identity module.

A booking needs to know that the branch exists and which customer profile
belongs to the account it was asked to book for. Both are reads of tables the
identity module owns, so they sit behind ports named for that module.

The branch directory is the read side of the same module. It lists the trading
branches for a visitor, and an availability search uses it to check the branch
it was asked about.

Signing in, staying signed in and signing out need four more. The account
repository and the session repository are storage. The password verifier and
the access token issuer are the two pieces of cryptography, kept behind ports
so the use cases can be tested without a work factor and without a signing key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.identity.read_models import BranchListing
from app.domain.account import Account
from app.domain.enums import RevokeReason
from app.domain.identity import Branch, CustomerProfile
from app.domain.session import RefreshSession


class BranchDirectory(Protocol):
    """The trading branches, as a visitor may see them."""

    def list_active(self) -> list[BranchListing]:
        """Return every active branch, ordered by name and then by code."""
        ...


class BranchRepository(Protocol):
    """Read access to the trading branches."""

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key, or None when there is none."""
        ...


class CustomerRepository(Protocol):
    """Read access to customer profiles."""

    def profile_for_account(self, user_account_id: UUID) -> CustomerProfile | None:
        """Return the customer profile that belongs to a sign in account.

        Returns:
            The profile, or None when the account has none. Staff accounts have
            none, and an account that is not a customer cannot own a booking.

        """
        ...


class AccountRepository(Protocol):
    """Where sign in accounts are read, and where the lockout state is written."""

    def find_by_email_for_update(self, email: str) -> Account | None:
        """Return the account with this address, locked for the rest of the transaction.

        The row is locked so that two sign ins for one account cannot both
        read the same failure count and both write it back one higher.
        """
        ...

    def get(self, account_id: UUID) -> Account | None:
        """Return the account with this key as it is stored now, or None."""
        ...

    def save_login_state(self, account: Account) -> None:
        """Write the failure count, the lock and the last sign in of an account."""
        ...


class SessionRepository(Protocol):
    """Where refresh sessions are stored."""

    def add(self, session: RefreshSession) -> None:
        """Write a new session inside the current transaction."""
        ...

    def find_by_token_hash_for_update(self, token_hash: str) -> RefreshSession | None:
        """Return the session a token hash names, locked for the rest of the transaction.

        The lock is what makes rotation safe. Of two requests that present the
        same token, the second waits and then finds the token already used.
        """
        ...

    def save_rotation(self, session: RefreshSession) -> None:
        """Write that a session was used, with when and why it stopped."""
        ...

    def revoke_family(
        self, *, user_account_id: UUID, family_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Revoke every live session of a family and return how many there were."""
        ...


class PasswordVerifier(Protocol):
    """Checks a presented password against a stored hash."""

    def verify(self, plain_password: str, stored_hash: str | None) -> bool:
        """Return True when the password matches the hash.

        Args:
            plain_password: The password as it was typed.
            stored_hash: The hash of the account, or None when there is no
                account to check against. An implementation does the same
                amount of work either way and answers False for None, so the
                time a refusal takes says nothing about why (BR-46).

        """
        ...


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    """A signed access token and how long it lives.

    Attributes:
        value: The encoded token. Left out of the representation on purpose.
        expires_in: Its lifetime in seconds.

    """

    value: str = field(repr=False)
    expires_in: int


class AccessTokenIssuer(Protocol):
    """Signs the short lived access token of a signed in account."""

    def issue(self, account: Account, issued_at: datetime) -> IssuedAccessToken:
        """Return an access token for the account, issued at the given instant."""
        ...
