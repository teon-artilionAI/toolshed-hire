"""The throttle rules of the account routes, and how an attempt is counted (C-17).

Registration, the verification link, the request to send it again and the two
halves of a password reset are each counted before any other work is done.
Going over a limit is answered with a wait, and nothing is hashed, looked up
or sent for an attempt that was refused.

A route that anybody can call is counted for the client address it came from.
The two that send a message to an address somebody typed are counted for that
address as well, in a window of an hour, so one mailbox cannot be filled by
asking again and again. The request to send the verification link again is
counted for the account that asked.

The counting is a transaction of its own, committed before the work starts.
That keeps the lock on a counter row to the length of one statement, and it
means an attempt is counted even when what follows it fails. Signing in does
the same and uses `seconds_to_wait` from here.

The limits below are the defaults. The composition root passes the configured
ones. The windows are not settings.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final

from app.application.identity.sessions import ClientDetails
from app.application.throttle import RateLimitStore, Throttle, ThrottleRule
from app.application.unit_of_work import UnitOfWork
from app.domain.errors import TooManyAttempts

logger = logging.getLogger(__name__)

# What every client whose address the server could not work out is counted
# under. They share one window, which errs towards refusing.
UNKNOWN_ADDRESS_SUBJECT: Final[str] = "unknown-address"

ACCOUNT_ATTEMPT_WINDOW: Final[timedelta] = timedelta(minutes=15)
ACCOUNT_MAIL_WINDOW: Final[timedelta] = timedelta(hours=1)

REGISTER_ATTEMPTS_PER_EMAIL: Final[int] = 5
REGISTER_ATTEMPTS_PER_ADDRESS: Final[int] = 10
VERIFICATION_ATTEMPTS_PER_ADDRESS: Final[int] = 20
VERIFICATION_RESENDS_PER_ACCOUNT: Final[int] = 5
RESET_REQUESTS_PER_EMAIL: Final[int] = 5
RESET_REQUESTS_PER_ADDRESS: Final[int] = 10
RESET_COMPLETIONS_PER_ADDRESS: Final[int] = 10

ACCOUNT_ATTEMPTS_MESSAGE: Final[str] = (
    "Too many attempts. Wait for the time given in Retry-After and try again."
)


@dataclass(frozen=True, slots=True)
class AccountThrottleRules:
    """The seven rules the account routes are counted against.

    Attributes:
        register_email: Registrations naming one email address, in an hour.
        register_address: Registrations from one client address.
        verification_address: Verification links presented from one client address.
        resend_account: Requests by one account to be sent its link again, in an hour.
        reset_request_email: Reset requests naming one email address, in an hour.
        reset_request_address: Reset requests from one client address.
        reset_completion_address: Reset links presented from one client address.

    """

    register_email: ThrottleRule = ThrottleRule(
        name="register-email", limit=REGISTER_ATTEMPTS_PER_EMAIL, window=ACCOUNT_MAIL_WINDOW
    )
    register_address: ThrottleRule = ThrottleRule(
        name="register-address",
        limit=REGISTER_ATTEMPTS_PER_ADDRESS,
        window=ACCOUNT_ATTEMPT_WINDOW,
    )
    verification_address: ThrottleRule = ThrottleRule(
        name="verification-address",
        limit=VERIFICATION_ATTEMPTS_PER_ADDRESS,
        window=ACCOUNT_ATTEMPT_WINDOW,
    )
    resend_account: ThrottleRule = ThrottleRule(
        name="verification-resend-account",
        limit=VERIFICATION_RESENDS_PER_ACCOUNT,
        window=ACCOUNT_MAIL_WINDOW,
    )
    reset_request_email: ThrottleRule = ThrottleRule(
        name="reset-request-email",
        limit=RESET_REQUESTS_PER_EMAIL,
        window=ACCOUNT_MAIL_WINDOW,
    )
    reset_request_address: ThrottleRule = ThrottleRule(
        name="reset-request-address",
        limit=RESET_REQUESTS_PER_ADDRESS,
        window=ACCOUNT_ATTEMPT_WINDOW,
    )
    reset_completion_address: ThrottleRule = ThrottleRule(
        name="reset-completion-address",
        limit=RESET_COMPLETIONS_PER_ADDRESS,
        window=ACCOUNT_ATTEMPT_WINDOW,
    )

    def with_limits(
        self,
        *,
        register_per_email: int,
        register_per_address: int,
        verification_per_address: int,
        resends_per_account: int,
        reset_requests_per_email: int,
        reset_requests_per_address: int,
        reset_completions_per_address: int,
    ) -> AccountThrottleRules:
        """Return the seven rules with other limits, keeping their names and their windows.

        Raises:
            ValueError: If any limit is below one.

        """
        return AccountThrottleRules(
            register_email=replace(self.register_email, limit=register_per_email),
            register_address=replace(self.register_address, limit=register_per_address),
            verification_address=replace(
                self.verification_address, limit=verification_per_address
            ),
            resend_account=replace(self.resend_account, limit=resends_per_account),
            reset_request_email=replace(
                self.reset_request_email, limit=reset_requests_per_email
            ),
            reset_request_address=replace(
                self.reset_request_address, limit=reset_requests_per_address
            ),
            reset_completion_address=replace(
                self.reset_completion_address, limit=reset_completions_per_address
            ),
        )


DEFAULT_ACCOUNT_RULES: Final[AccountThrottleRules] = AccountThrottleRules()

# One rule and the subject an attempt is counted under.
type Counted = tuple[ThrottleRule, str]


def address_subject(client: ClientDetails) -> str:
    """Return what the attempts of one client are counted under."""
    return str(client.address) if client.address is not None else UNKNOWN_ADDRESS_SUBJECT


def seconds_to_wait(
    throttle: Throttle, store: RateLimitStore, counted: Sequence[Counted], now: datetime
) -> int:
    """Count one attempt against every rule and return the wait, or zero when allowed.

    Every rule is counted, also once one of them has refused, so a caller who
    is over one limit still uses up the others.
    """
    verdicts = [throttle.check(store, rule, subject, now) for rule, subject in counted]
    return max(
        (verdict.retry_after_seconds for verdict in verdicts if not verdict.allowed), default=0
    )


def count_attempt(
    uow: UnitOfWork, throttle: Throttle, counted: Sequence[Counted], now: datetime
) -> None:
    """Count one attempt in a transaction of its own, and refuse it when it is one too many.

    Args:
        uow: The unit of work. It is entered here and committed before this returns.
        throttle: Counts the attempt.
        counted: Each rule with the subject the attempt is counted under.
        now: The current instant, from the clock.

    Raises:
        TooManyAttempts: If the attempt went over any of the rules.

    """
    with uow as open_uow:
        retry_after = seconds_to_wait(throttle, open_uow.rate_limits, counted, now)
        open_uow.commit()
    if retry_after:
        logger.warning(
            "auth.attempt_throttled",
            extra={
                "rules": [rule.name for rule, _subject in counted],
                "retry_after_seconds": retry_after,
            },
        )
        raise TooManyAttempts(ACCOUNT_ATTEMPTS_MESSAGE, retry_after_seconds=retry_after)
