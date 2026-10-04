"""The two halves of a password reset (US-04, BR-45, C-18, R-13).

`RequestPasswordResetUseCase` is asked with an email address and answers the
same way whether or not the address has an account (C-14). A token is minted
and hashed on both paths, and one audit event is written on both. An address
with an active account has the token stored and is sent the link. Any other
address is sent nothing, so that request comes back sooner by the time the
email provider takes to answer. I accept that difference. Sending a message
to an address that has no account would mean writing to strangers.

`CompletePasswordResetUseCase` redeems the token. In one transaction it sets
the new hash, clears the token, lifts any lock, marks the email address as
verified when it was not yet and revokes every refresh session of the
account, so a browser that was signed in with the old password is signed out.
The link only ever went to that address, so using it proves the person reads
mail there, and a new member of staff, who chooses a first password through
this link, ends verified. The sessions are revoked with the reason `LOGOUT`.
The holder of the account ended them, no administrator did, and the audit
event of the reset says exactly why, with the lock and the verification
before and after. A token that is unknown, already used or out of time is
refused with one sentence.

Both are counted before they do anything, and a new password is hashed before
the transaction opens, so no row is held while the work factor runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.identity.account_mail import AccountMailer, MailExpectation
from app.application.identity.account_rules import ensure_password_may_be_set, normalised_email
from app.application.identity.attempts import (
    DEFAULT_ACCOUNT_RULES,
    AccountThrottleRules,
    address_subject,
    count_attempt,
)
from app.application.identity.ports import PasswordHasher
from app.application.identity.sessions import ACCOUNT_ENTITY_TYPE, ClientDetails
from app.application.identity.sign_in import UNKNOWN_ACCOUNT_ID
from app.application.throttle import Throttle
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.account import Account
from app.domain.account_tokens import PendingToken, hash_account_token, mint_account_token
from app.domain.enums import RevokeReason
from app.domain.errors import ResetLinkInvalid

logger = logging.getLogger(__name__)

RESET_REQUESTED_ACTION: Final[str] = "auth.password_reset_requested"
RESET_COMPLETED_ACTION: Final[str] = "auth.password_reset_completed"
NEW_PASSWORD_PARAMETER: Final[str] = "newPassword"
# The nearest reason the schema has. The holder of the account ended the
# sessions by choosing a new password, which is closer to signing out
# everywhere than to anything an administrator did.
RESET_REVOKE_REASON: Final[RevokeReason] = RevokeReason.LOGOUT
RESET_LINK_INVALID_MESSAGE: Final[str] = (
    "This reset link is not valid any more. Ask for a new one and try again."
)
UNKNOWN_LINK: Final[str] = "unknown-or-used"
EXPIRED_LINK: Final[str] = "expired"


@dataclass(frozen=True, slots=True)
class RequestPasswordResetCommand:
    """A request for a reset link.

    Attributes:
        email: The address as it was typed.
        client: Where the request came from.

    """

    email: str
    client: ClientDetails = field(default_factory=ClientDetails)


class RequestPasswordResetUseCase(UseCase[RequestPasswordResetCommand, MailExpectation]):
    """Issue a reset token for an address that has an account, and say nothing either way."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        throttle: Throttle,
        mailer: AccountMailer,
        rules: AccountThrottleRules = DEFAULT_ACCOUNT_RULES,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            throttle: Counts the request for the address and for the client.
            mailer: Sends the message once the transaction has committed.
            rules: The limits of the windows. The defaults when omitted.

        """
        super().__init__(uow, clock)
        self._throttle = throttle
        self._mailer = mailer
        self._rules = rules

    def execute(self, command: RequestPasswordResetCommand) -> MailExpectation:
        """Store a reset token and send its link, when the address has an active account.

        Returns:
            Whether a message for the address would be delivered here. It is
            the same whether or not the address has an account.

        Raises:
            TooManyAttempts: If the address or the client went over its window.

        """
        now = self._clock.now()
        email = normalised_email(command.email)
        logger.info(
            "auth.reset_request_started",
            extra={"client_address_known": command.client.address is not None},
        )
        counted = (
            (self._rules.reset_request_email, email),
            (self._rules.reset_request_address, address_subject(command.client)),
        )
        count_attempt(self._uow, self._throttle, counted, now)
        # Minted and hashed on every path, so a known address costs no more.
        token = mint_account_token()
        pending = PendingToken.for_password_reset(token, now)
        with self._uow as uow:
            account = uow.accounts.find_by_email_for_update(email)
            issued = account is not None and account.is_active
            if account is not None and issued:
                account.start_password_reset(pending)
                uow.accounts.save_security_state(account)
            uow.audit.record(
                audit_event_for(
                    actor=None,
                    entity_type=ACCOUNT_ENTITY_TYPE,
                    entity_id=account.id if account is not None else UNKNOWN_ACCOUNT_ID,
                    action=RESET_REQUESTED_ACTION,
                    occurred_at=now,
                    after_state={"link_issued": issued},
                )
            )
            uow.commit()
        if issued:
            self._mailer.send_password_reset(to=email, token=token)
        logger.info("auth.reset_request_finished", extra={"link_issued": issued})
        return self._mailer.expectation_for(email)


@dataclass(frozen=True, slots=True)
class CompletePasswordResetCommand:
    """A request to choose a new password with a reset token.

    Attributes:
        token: The token from the link. Kept out of the representation.
        new_password: The password as it was typed. Kept out of the representation.
        client: Where the request came from.

    """

    token: str = field(repr=False)
    new_password: str = field(repr=False)
    client: ClientDetails = field(default_factory=ClientDetails)


class CompletePasswordResetUseCase(UseCase[CompletePasswordResetCommand, None]):
    """Redeem a reset token, set the new password and end every session."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        passwords: PasswordHasher,
        throttle: Throttle,
        rules: AccountThrottleRules = DEFAULT_ACCOUNT_RULES,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            passwords: Hashes the new password.
            throttle: Counts the attempt for the client address.
            rules: The limits of the windows. The defaults when omitted.

        """
        super().__init__(uow, clock)
        self._passwords = passwords
        self._throttle = throttle
        self._rules = rules

    def execute(self, command: CompletePasswordResetCommand) -> None:
        """Set the new password of the account that holds this token.

        Raises:
            TooManyAttempts: If the client went over its window.
            ValidationFailure: If the new password breaks the password rule.
            ResetLinkInvalid: If the token is unknown, used or out of time.
                The message is the same for all three.

        """
        now = self._clock.now()
        logger.info("auth.reset_completion_started")
        counted = ((self._rules.reset_completion_address, address_subject(command.client)),)
        count_attempt(self._uow, self._throttle, counted, now)
        ensure_password_may_be_set(command.new_password, NEW_PASSWORD_PARAMETER)
        new_hash = self._passwords.hash(command.new_password)
        with self._uow as uow:
            account = uow.accounts.find_by_password_reset_hash_for_update(
                hash_account_token(command.token)
            )
            refusal = self._redeem(uow, account, command.token, new_hash, now)
            uow.commit()
        if refusal is not None:
            logger.warning("auth.reset_completion_refused", extra={"reason": refusal})
            raise ResetLinkInvalid(RESET_LINK_INVALID_MESSAGE)
        logger.info("auth.reset_completion_finished")

    def _redeem(
        self, uow: UnitOfWork, account: Account | None, token: str, new_hash: str, now: datetime
    ) -> str | None:
        """Redeem the token and record it, or return why it was refused."""
        if account is None:
            return UNKNOWN_LINK
        was_locked = account.is_locked(now)
        was_verified = account.email_verified
        if not account.reset_password(token, new_hash, now):
            return EXPIRED_LINK
        uow.accounts.save_security_state(account)
        revoked_count = uow.sessions.revoke_all_for_account(
            user_account_id=account.id, reason=RESET_REVOKE_REASON, at=now
        )
        uow.audit.record(
            audit_event_for(
                actor=account.as_actor(),
                entity_type=ACCOUNT_ENTITY_TYPE,
                entity_id=account.id,
                action=RESET_COMPLETED_ACTION,
                occurred_at=now,
                before_state={"locked": was_locked, "email_verified": was_verified},
                after_state={
                    "locked": False,
                    "email_verified": account.email_verified,
                    "revoked_session_count": revoked_count,
                    "revoke_reason": RESET_REVOKE_REASON.value,
                },
            )
        )
        logger.info(
            "auth.reset_completion_written",
            extra={
                "user_id": str(account.id),
                "revoked_session_count": revoked_count,
                "email_verified_now": not was_verified,
            },
        )
        return None
