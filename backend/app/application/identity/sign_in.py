"""The use case that signs somebody in (BR-45, BR-46, BR-48).

Four things can be wrong with a sign in. The address is unknown, the account is
deactivated, the account is locked or the password is wrong. The caller is told
the same thing in all four cases, in the same words, after the same amount of
work. Exactly one password verification runs on every path, against a dummy
hash when there is no account to check, so the time the answer takes does not
give the reason away either. The reason is written to the audit trail and to
the log, on the server only.

Every attempt is counted against two fixed windows before anything else is
looked at, one for the address being signed in to and one for the client
address it came from (C-17). Going over either is answered with a wait and no
password is checked.

A refusal is still a change. The failure count moves and an audit event is
written, so the unit of work is committed before the refusal is raised.

The counting and the password check are two transactions, one after the other.
Counting locks the two counter rows, and a password check takes a quarter of a
second. Held together, every sign in from one client address would queue
behind the one before it for that long. Committing the counters first keeps
their locks to the length of one statement, and it means an attempt is counted
even when what follows it fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.identity.ports import AccessTokenIssuer, PasswordVerifier
from app.application.identity.sessions import (
    ACCOUNT_ENTITY_TYPE,
    ClientDetails,
    SessionGrant,
    grant_session,
)
from app.application.throttle import Throttle, ThrottleRule
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.account import Account
from app.domain.errors import InvalidCredentials, TooManyAttempts
from app.domain.session import RefreshSession, hash_refresh_token, mint_refresh_token

logger = logging.getLogger(__name__)

LOGIN_WINDOW: Final[timedelta] = timedelta(minutes=15)
# The limits the design document sets. The use case is handed its limits, and
# these are the defaults. The composition root passes the configured ones.
LOGIN_ATTEMPTS_PER_EMAIL: Final[int] = 10
LOGIN_ATTEMPTS_PER_ADDRESS: Final[int] = 30
LOGIN_EMAIL_RULE: Final[ThrottleRule] = ThrottleRule(
    name="login-email", limit=LOGIN_ATTEMPTS_PER_EMAIL, window=LOGIN_WINDOW
)
LOGIN_ADDRESS_RULE: Final[ThrottleRule] = ThrottleRule(
    name="login-address", limit=LOGIN_ATTEMPTS_PER_ADDRESS, window=LOGIN_WINDOW
)
# What every client whose address the server could not work out is counted
# under. They share one window, which errs towards refusing.
UNKNOWN_ADDRESS_SUBJECT: Final[str] = "unknown-address"

LOGIN_FAILED_ACTION: Final[str] = "auth.login_failed"
LOGIN_SUCCEEDED_ACTION: Final[str] = "auth.login_succeeded"
# The entity an audit event names when the address belongs to no account.
UNKNOWN_ACCOUNT_ID: Final[UUID] = UUID(int=0)

INVALID_CREDENTIALS_MESSAGE: Final[str] = (
    "Sign in failed. The email address or the password is wrong, or the account cannot "
    "sign in at the moment. No further detail is given deliberately."
)
TOO_MANY_ATTEMPTS_MESSAGE: Final[str] = (
    "Too many sign in attempts. Wait for the time given in Retry-After and try again."
)


class LoginFailure(str, Enum):
    """Why a sign in was refused. Recorded on the server and never returned."""

    UNKNOWN_EMAIL = "unknown-email"
    DEACTIVATED = "deactivated"
    LOCKED = "locked"
    WRONG_PASSWORD = "wrong-password"


@dataclass(frozen=True, slots=True)
class LoginThrottleRules:
    """The two rules every sign in attempt is counted against.

    Attributes:
        email: The rule for the address being signed in to.
        address: The rule for the client address the attempt came from.

    """

    email: ThrottleRule = LOGIN_EMAIL_RULE
    address: ThrottleRule = LOGIN_ADDRESS_RULE

    @classmethod
    def with_limits(cls, *, per_email: int, per_address: int) -> LoginThrottleRules:
        """Return the two rules with other limits, keeping their names and their window.

        Raises:
            ValueError: If either limit is below one.

        """
        return cls(
            email=replace(LOGIN_EMAIL_RULE, limit=per_email),
            address=replace(LOGIN_ADDRESS_RULE, limit=per_address),
        )


DEFAULT_LOGIN_RULES: Final[LoginThrottleRules] = LoginThrottleRules()


@dataclass(frozen=True, slots=True)
class SignInCommand:
    """A request to sign in.

    Attributes:
        email: The address as it was typed.
        password: The password as it was typed. Kept out of the representation.
        client: Where the request came from.

    """

    email: str
    password: str = field(repr=False)
    client: ClientDetails = field(default_factory=ClientDetails)


class SignInUseCase(UseCase[SignInCommand, SessionGrant]):
    """Check a password, keep the lockout and open a session."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        passwords: PasswordVerifier,
        tokens: AccessTokenIssuer,
        throttle: Throttle,
        rules: LoginThrottleRules = DEFAULT_LOGIN_RULES,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            passwords: Verifies a password against a stored hash.
            tokens: Signs the access token.
            throttle: Counts the attempt against the two sign in windows.
            rules: The limits of the two windows. The defaults when omitted.

        """
        super().__init__(uow, clock)
        self._passwords = passwords
        self._tokens = tokens
        self._throttle = throttle
        self._rules = rules

    def execute(self, command: SignInCommand) -> SessionGrant:
        """Sign the caller in, or refuse without saying why.

        Raises:
            TooManyAttempts: If the address or the client went over its window.
            InvalidCredentials: If the sign in was refused for any other
                reason. The message is the same whatever the reason was.

        """
        now = self._clock.now()
        email = command.email.strip().lower()
        logger.info(
            "auth.login_started",
            extra={"client_address_known": command.client.address is not None},
        )
        with self._uow as uow:
            retry_after = self._seconds_to_wait(uow, email, command.client, now)
            uow.commit()
        if retry_after:
            logger.warning("auth.login_throttled", extra={"retry_after_seconds": retry_after})
            raise TooManyAttempts(TOO_MANY_ATTEMPTS_MESSAGE, retry_after_seconds=retry_after)
        with self._uow as uow:
            outcome = self._attempt(uow, email, command, now)
            uow.commit()
        if not isinstance(outcome, SessionGrant):
            raise InvalidCredentials(INVALID_CREDENTIALS_MESSAGE)
        logger.info(
            "auth.login_succeeded",
            extra={"user_id": str(outcome.account.id), "role": outcome.account.role.value},
        )
        return outcome

    def _seconds_to_wait(
        self, uow: UnitOfWork, email: str, client: ClientDetails, now: datetime
    ) -> int:
        """Count the attempt in both windows and return the wait, or zero when allowed."""
        address = str(client.address) if client.address is not None else UNKNOWN_ADDRESS_SUBJECT
        verdicts = [
            self._throttle.check(uow.rate_limits, self._rules.email, email, now),
            self._throttle.check(uow.rate_limits, self._rules.address, address, now),
        ]
        return max(
            (verdict.retry_after_seconds for verdict in verdicts if not verdict.allowed),
            default=0,
        )

    def _attempt(
        self, uow: UnitOfWork, email: str, command: SignInCommand, now: datetime
    ) -> SessionGrant | LoginFailure:
        """Check the password and write the outcome. Nothing is committed here."""
        account = uow.accounts.find_by_email_for_update(email)
        barred = _reason_barred(account, now)
        # One verification on every path. With no usable account the verifier
        # is handed no hash, and it spends the same time on a dummy one.
        usable_hash = account.password_hash if account is not None and barred is None else None
        password_matches = self._passwords.verify(command.password, usable_hash)

        if account is None or barred is not None:
            return self._refuse(uow, account, barred or LoginFailure.UNKNOWN_EMAIL, now)
        if not password_matches:
            account.record_failed_login(now)
            uow.accounts.save_login_state(account)
            return self._refuse(uow, account, LoginFailure.WRONG_PASSWORD, now)

        account.record_successful_login(now)
        uow.accounts.save_login_state(account)
        refresh_token = mint_refresh_token()
        session = RefreshSession.opened_at_sign_in(
            user_account_id=account.id,
            token_hash=hash_refresh_token(refresh_token),
            now=now,
            user_agent=command.client.user_agent,
            ip_address=command.client.address,
        )
        uow.sessions.add(session)
        uow.audit.record(
            audit_event_for(
                actor=account.as_actor(),
                entity_type=ACCOUNT_ENTITY_TYPE,
                entity_id=account.id,
                action=LOGIN_SUCCEEDED_ACTION,
                occurred_at=now,
                after_state={"session_family_id": str(session.family_id)},
            )
        )
        return grant_session(
            uow,
            self._tokens,
            account=account,
            session=session,
            refresh_token=refresh_token,
            now=now,
        )

    def _refuse(
        self, uow: UnitOfWork, account: Account | None, reason: LoginFailure, now: datetime
    ) -> LoginFailure:
        """Record a refused sign in in the audit trail and the log, and return its reason."""
        failed_count = account.failed_login_count if account is not None else 0
        locked = account.is_locked(now) if account is not None else False
        uow.audit.record(
            audit_event_for(
                actor=None,
                entity_type=ACCOUNT_ENTITY_TYPE,
                entity_id=account.id if account is not None else UNKNOWN_ACCOUNT_ID,
                action=LOGIN_FAILED_ACTION,
                occurred_at=now,
                after_state={
                    "reason": reason.value,
                    "failed_login_count": failed_count,
                    "locked": locked,
                },
            )
        )
        logger.warning(
            "auth.login_refused",
            extra={
                "reason": reason.value,
                "user_id": str(account.id) if account is not None else None,
                "failed_login_count": failed_count,
                "locked": locked,
            },
        )
        return reason


def _reason_barred(account: Account | None, now: datetime) -> LoginFailure | None:
    """Return why an account may not sign in whatever the password, or None."""
    if account is None:
        return LoginFailure.UNKNOWN_EMAIL
    if not account.is_active:
        return LoginFailure.DEACTIVATED
    if account.is_locked(now):
        return LoginFailure.LOCKED
    return None
