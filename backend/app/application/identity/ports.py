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

Registration, the two single use tokens and the customer's own profile write
through the same repositories, and the password hasher is the third piece of
cryptography behind a port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.identity.read_models import BranchListing
from app.domain.account import Account
from app.domain.customer_account import CustomerDetails, NewCustomer
from app.domain.enums import RevokeReason
from app.domain.identity import Branch, CustomerProfile
from app.domain.session import RefreshSession
from app.domain.walk_in import WalkInCustomer


class EmailAlreadyRegistered(Exception):
    """Raised by the account repository when an address was taken a moment earlier.

    A registration looks the address up before it writes. Two registrations
    for one new address can both find nothing, and the database then lets one
    of them in. The other is told with this, so it can answer as it would have
    for an address that already had an account.
    """


class BranchDirectory(Protocol):
    """The trading branches, as a visitor may see them."""

    def list_active(self) -> list[BranchListing]:
        """Return every active branch, ordered by name and then by code."""
        ...


class BranchRepository(Protocol):
    """Read access to the branches."""

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key, or None when there is none."""
        ...

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the trading branch with this code, or None when there is none.

        A branch that has stopped trading is answered with None, because
        nothing can be collected there.
        """
        ...


class CustomerRepository(Protocol):
    """Customer profiles, as far as a booking reads and counts on them."""

    def profile_for_account(self, user_account_id: UUID) -> CustomerProfile | None:
        """Return the customer profile that belongs to a sign in account.

        Returns:
            The profile, or None when the account has none. Staff accounts have
            none, and an account that is not a customer cannot own a booking.

        """
        ...

    def get(self, customer_profile_id: UUID) -> CustomerProfile | None:
        """Return the customer profile with this key, or None when there is none.

        A walk-in has a profile and no account, so this is how staff name the
        customer a counter booking is for.
        """
        ...

    def record_late_cancellation(self, customer_profile_id: UUID) -> None:
        """Count one late cancellation on a customer profile (BR-16).

        The count is raised by one in the database, so two cancellations at
        the same moment are both counted.
        """
        ...

    def add_registered(
        self, *, user_account_id: UUID, registered_branch_id: UUID, customer: NewCustomer
    ) -> UUID:
        """Write the profile of somebody who has just registered and return its key."""
        ...

    def add_walk_in(self, *, registered_branch_id: UUID, customer: WalkInCustomer) -> UUID:
        """Write the profile of a walk-in, which has no account, and return its key."""
        ...

    def details_for_account(
        self, user_account_id: UUID, *, for_update: bool = False
    ) -> CustomerDetails | None:
        """Return a customer's own details, or None when the account has no profile.

        Args:
            user_account_id: The sign in account the profile belongs to.
            for_update: True to lock the profile and the account for the rest
                of the transaction, which an edit asks for.

        """
        ...

    def save_details(self, details: CustomerDetails) -> None:
        """Write the contact and billing fields of a customer, on both rows.

        The name and the phone number are kept on the account and on the
        profile, and both copies are written here so they cannot drift apart.
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

    def get_for_update(self, account_id: UUID) -> Account | None:
        """Return the account with this key, locked for the rest of the transaction."""
        ...

    def find_by_email_verification_hash_for_update(self, token_hash: str) -> Account | None:
        """Return the account holding this verification token hash, locked, or None."""
        ...

    def find_by_password_reset_hash_for_update(self, token_hash: str) -> Account | None:
        """Return the account holding this reset token hash, locked, or None."""
        ...

    def add(self, account: Account) -> None:
        """Write a new account inside the current transaction.

        Raises:
            EmailAlreadyRegistered: If another transaction took the address
                between the lookup and this write.

        """
        ...

    def save_login_state(self, account: Account) -> None:
        """Write the failure count, the lock and the last sign in of an account."""
        ...

    def save_security_state(self, account: Account) -> None:
        """Write the password hash, the verification, the two tokens and the lockout."""
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

    def revoke_all_for_account(
        self, *, user_account_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Revoke every live session of an account, whatever its family, and return how many."""
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


class PasswordHasher(Protocol):
    """Turns a chosen password into the hash that is stored."""

    def hash(self, plain_password: str) -> str:
        """Return the hash of a password. The password itself is never kept."""
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
