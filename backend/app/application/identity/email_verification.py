"""The two use cases behind a verified email address (US-02, BR-47, C-18).

`VerifyEmailUseCase` redeems the token of a verification link. The token is
looked up by its SHA-256, redeemed once and cleared. A token that is unknown,
already used or out of time is refused with one sentence, so the answer does
not say which it was. The reason goes to the log.

`ResendVerificationUseCase` sends a signed in account a new link. The new
token replaces the old one, so the link in the earlier message stops working.
An account that is already verified is answered in the same way and nothing
is sent, because there is nothing left to prove.

Both are counted before they do anything, the first for the client address
and the second for the account.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.identity.account_mail import AccountMailer, MailExpectation
from app.application.identity.attempts import (
    DEFAULT_ACCOUNT_RULES,
    AccountThrottleRules,
    address_subject,
    count_attempt,
)
from app.application.identity.sessions import ACCOUNT_ENTITY_TYPE, ClientDetails
from app.application.throttle import Throttle
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.account import Account
from app.domain.account_tokens import PendingToken, hash_account_token, mint_account_token
from app.domain.errors import AuthenticationFailure, VerificationLinkInvalid
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

EMAIL_VERIFIED_ACTION: Final[str] = "auth.email_verified"
VERIFICATION_RESENT_ACTION: Final[str] = "auth.verification_resent"
VERIFICATION_LINK_INVALID_MESSAGE: Final[str] = (
    "This verification link is not valid any more. Sign in and ask for a new one."
)
UNKNOWN_LINK: Final[str] = "unknown-or-used"
EXPIRED_LINK: Final[str] = "expired"


@dataclass(frozen=True, slots=True)
class VerifyEmailCommand:
    """A request to prove an email address.

    Attributes:
        token: The token from the link. Kept out of the representation.
        client: Where the request came from.

    """

    token: str = field(repr=False)
    client: ClientDetails = field(default_factory=ClientDetails)


class VerifyEmailUseCase(UseCase[VerifyEmailCommand, None]):
    """Redeem a verification token, once."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        throttle: Throttle,
        rules: AccountThrottleRules = DEFAULT_ACCOUNT_RULES,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            throttle: Counts the attempt for the client address.
            rules: The limits of the windows. The defaults when omitted.

        """
        super().__init__(uow, clock)
        self._throttle = throttle
        self._rules = rules

    def execute(self, command: VerifyEmailCommand) -> None:
        """Mark the address of the account that holds this token as proved.

        Raises:
            TooManyAttempts: If the client went over its window.
            VerificationLinkInvalid: If the token is unknown, used or out of
                time. The message is the same for all three.

        """
        now = self._clock.now()
        logger.info("auth.email_verification_started")
        counted = ((self._rules.verification_address, address_subject(command.client)),)
        count_attempt(self._uow, self._throttle, counted, now)
        with self._uow as uow:
            account = uow.accounts.find_by_email_verification_hash_for_update(
                hash_account_token(command.token)
            )
            refusal = self._redeem(uow, account, command.token, now)
            uow.commit()
        if refusal is not None:
            logger.warning("auth.email_verification_refused", extra={"reason": refusal})
            raise VerificationLinkInvalid(VERIFICATION_LINK_INVALID_MESSAGE)
        logger.info("auth.email_verification_finished")

    def _redeem(
        self, uow: UnitOfWork, account: Account | None, token: str, now: datetime
    ) -> str | None:
        """Redeem the token and record it, or return why it was refused."""
        if account is None:
            return UNKNOWN_LINK
        was_verified = account.email_verified
        if not account.verify_email(token, now):
            return EXPIRED_LINK
        uow.accounts.save_security_state(account)
        uow.audit.record(
            audit_event_for(
                actor=account.as_actor(),
                entity_type=ACCOUNT_ENTITY_TYPE,
                entity_id=account.id,
                action=EMAIL_VERIFIED_ACTION,
                occurred_at=now,
                before_state={"email_verified": was_verified},
                after_state={"email_verified": True},
            )
        )
        return None


@dataclass(frozen=True, slots=True)
class ResendVerificationCommand:
    """A request by a signed in account to be sent its verification link again.

    Attributes:
        actor: The account that is asking.

    """

    actor: Actor


class ResendVerificationUseCase(UseCase[ResendVerificationCommand, MailExpectation]):
    """Send a signed in account a new verification link, unless it is already verified."""

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
            throttle: Counts the request for the account.
            mailer: Sends the message once the transaction has committed.
            rules: The limits of the windows. The defaults when omitted.

        """
        super().__init__(uow, clock)
        self._throttle = throttle
        self._mailer = mailer
        self._rules = rules

    def execute(self, command: ResendVerificationCommand) -> MailExpectation:
        """Issue a new token and send it, or do nothing for a verified account.

        Returns:
            Whether a message for the address of the account would be
            delivered here, whether or not one was sent.

        Raises:
            TooManyAttempts: If the account went over its window.
            AuthenticationFailure: If the account no longer exists.

        """
        now = self._clock.now()
        actor = command.actor
        logger.info("auth.verification_resend_started", extra={"user_id": str(actor.user_id)})
        counted = ((self._rules.resend_account, str(actor.user_id)),)
        count_attempt(self._uow, self._throttle, counted, now)
        token = mint_account_token()
        with self._uow as uow:
            account = uow.accounts.get_for_update(actor.user_id)
            if account is None:
                raise AuthenticationFailure(
                    "Attempted to act as an account that no longer exists.",
                    {"reason": "unknown-subject"},
                )
            issued = not account.email_verified
            if issued:
                account.start_email_verification(PendingToken.for_email_verification(token, now))
                uow.accounts.save_security_state(account)
                uow.audit.record(
                    audit_event_for(
                        actor=actor,
                        entity_type=ACCOUNT_ENTITY_TYPE,
                        entity_id=account.id,
                        action=VERIFICATION_RESENT_ACTION,
                        occurred_at=now,
                        after_state={"email_verified": False},
                    )
                )
                uow.commit()
        if issued:
            self._mailer.send_verification(to=account.email, token=token)
        logger.info(
            "auth.verification_resend_finished",
            extra={"user_id": str(actor.user_id), "link_issued": issued},
        )
        return self._mailer.expectation_for(account.email)
