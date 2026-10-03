"""The attempt limits of the service, one setting for each (C-17).

Nine limits say how many attempts a throttle window allows. Two are for
signing in and seven are for the account routes, which are registration, the
verification link, the request to send it again and the two halves of a
password reset. Each is an environment variable with the default the
application layer states, so a limit has one default and it is not here.

No attribute name holds the word `password`. The start-up log shows every
limit under the name of its attribute, and the log filter blanks the value of
any key that holds that word.

They live in a class of their own so that `config.py` stays a list of the
other settings. `Settings` inherits from this class, so every limit is read
from the same environment in the same pass and is an attribute of the one
settings object.

The windows are not settings. A limit can be changed for an environment. How
long a window lasts is part of the rule.
"""

from __future__ import annotations

from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings

from app.application.identity.attempts import (
    REGISTER_ATTEMPTS_PER_ADDRESS,
    REGISTER_ATTEMPTS_PER_EMAIL,
    RESET_COMPLETIONS_PER_ADDRESS,
    RESET_REQUESTS_PER_ADDRESS,
    RESET_REQUESTS_PER_EMAIL,
    VERIFICATION_ATTEMPTS_PER_ADDRESS,
    VERIFICATION_RESENDS_PER_ACCOUNT,
)
from app.application.identity.sign_in import LOGIN_ATTEMPTS_PER_ADDRESS, LOGIN_ATTEMPTS_PER_EMAIL
from app.config_checks import AttemptLimit

# The environment variable of each limit, with the attribute that holds it and
# its default. The order is the order a failed start names them in.
ATTEMPT_LIMIT_SETTINGS: Final[tuple[tuple[str, str, int], ...]] = (
    ("LOGIN_ATTEMPTS_PER_EMAIL", "login_attempts_per_email", LOGIN_ATTEMPTS_PER_EMAIL),
    ("LOGIN_ATTEMPTS_PER_ADDRESS", "login_attempts_per_address", LOGIN_ATTEMPTS_PER_ADDRESS),
    ("REGISTER_ATTEMPTS_PER_EMAIL", "register_attempts_per_email", REGISTER_ATTEMPTS_PER_EMAIL),
    (
        "REGISTER_ATTEMPTS_PER_ADDRESS",
        "register_attempts_per_address",
        REGISTER_ATTEMPTS_PER_ADDRESS,
    ),
    (
        "VERIFICATION_ATTEMPTS_PER_ADDRESS",
        "verification_attempts_per_address",
        VERIFICATION_ATTEMPTS_PER_ADDRESS,
    ),
    (
        "VERIFICATION_RESENDS_PER_ACCOUNT",
        "verification_resends_per_account",
        VERIFICATION_RESENDS_PER_ACCOUNT,
    ),
    (
        "RESET_REQUESTS_PER_EMAIL",
        "reset_requests_per_email",
        RESET_REQUESTS_PER_EMAIL,
    ),
    (
        "RESET_REQUESTS_PER_ADDRESS",
        "reset_requests_per_address",
        RESET_REQUESTS_PER_ADDRESS,
    ),
    (
        "RESET_COMPLETIONS_PER_ADDRESS",
        "reset_completions_per_address",
        RESET_COMPLETIONS_PER_ADDRESS,
    ),
)
ATTEMPT_LIMIT_VARIABLES: Final[tuple[str, ...]] = tuple(
    variable for variable, _attribute, _default in ATTEMPT_LIMIT_SETTINGS
)


class AttemptLimitSettings(BaseSettings):
    """The nine attempt limits, one field per environment variable."""

    login_attempts_per_email: int = Field(
        default=LOGIN_ATTEMPTS_PER_EMAIL,
        validation_alias="LOGIN_ATTEMPTS_PER_EMAIL",
        description="Sign in attempts one email address may make in a window",
    )
    login_attempts_per_address: int = Field(
        default=LOGIN_ATTEMPTS_PER_ADDRESS,
        validation_alias="LOGIN_ATTEMPTS_PER_ADDRESS",
        description="Sign in attempts one client address may make in a window",
    )
    register_attempts_per_email: int = Field(
        default=REGISTER_ATTEMPTS_PER_EMAIL,
        validation_alias="REGISTER_ATTEMPTS_PER_EMAIL",
        description="Registrations that may name one email address in an hour",
    )
    register_attempts_per_address: int = Field(
        default=REGISTER_ATTEMPTS_PER_ADDRESS,
        validation_alias="REGISTER_ATTEMPTS_PER_ADDRESS",
        description="Registrations one client address may make in a window",
    )
    verification_attempts_per_address: int = Field(
        default=VERIFICATION_ATTEMPTS_PER_ADDRESS,
        validation_alias="VERIFICATION_ATTEMPTS_PER_ADDRESS",
        description="Verification links one client address may present in a window",
    )
    verification_resends_per_account: int = Field(
        default=VERIFICATION_RESENDS_PER_ACCOUNT,
        validation_alias="VERIFICATION_RESENDS_PER_ACCOUNT",
        description="Times one account may ask for its verification link again in an hour",
    )
    reset_requests_per_email: int = Field(
        default=RESET_REQUESTS_PER_EMAIL,
        validation_alias="RESET_REQUESTS_PER_EMAIL",
        description="Reset requests that may name one email address in an hour",
    )
    reset_requests_per_address: int = Field(
        default=RESET_REQUESTS_PER_ADDRESS,
        validation_alias="RESET_REQUESTS_PER_ADDRESS",
        description="Reset requests one client address may make in a window",
    )
    reset_completions_per_address: int = Field(
        default=RESET_COMPLETIONS_PER_ADDRESS,
        validation_alias="RESET_COMPLETIONS_PER_ADDRESS",
        description="Reset links one client address may present in a window",
    )

    def attempt_limits(self) -> tuple[AttemptLimit, ...]:
        """Return every limit as it was configured, with its variable and its default."""
        return tuple(
            AttemptLimit(variable=variable, value=int(getattr(self, attribute)), default=default)
            for variable, attribute, default in ATTEMPT_LIMIT_SETTINGS
        )

    def attempt_limit_values(self) -> dict[str, int]:
        """Return every limit by the name of its attribute, for the start-up log."""
        return {
            attribute: int(getattr(self, attribute))
            for _variable, attribute, _default in ATTEMPT_LIMIT_SETTINGS
        }
