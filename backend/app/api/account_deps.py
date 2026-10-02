"""The dependencies of registration, account security and the customer profile.

This is the third part of the composition root. `app/api/deps.py` wires the
unit of work, the clock and the email gateway, and `app/api/identity_deps.py`
wires signing in. This module puts those together into the use cases the
account routes and the profile routes call, and it is the only place that
knows bcrypt stands behind the password hasher.

The throttle rules are built once, as the module is imported, from the limits
the process was configured with. A limit the throttle cannot use then stops
the process as it starts and not at the first registration.

The account messages link to the frontend. The application factory reads the
origin from the configuration and keeps it on the application state, so an
application built for one environment links to the site of that environment.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Depends, Request

from app.api.deps import ClockDependency, NotificationGatewayDependency, UnitOfWorkDependency
from app.api.identity_deps import get_throttle
from app.application.identity.account_mail import AccountMailer
from app.application.identity.attempts import DEFAULT_ACCOUNT_RULES, AccountThrottleRules
from app.application.identity.email_verification import (
    ResendVerificationUseCase,
    VerifyEmailUseCase,
)
from app.application.identity.password_reset import (
    CompletePasswordResetUseCase,
    RequestPasswordResetUseCase,
)
from app.application.identity.ports import PasswordHasher
from app.application.identity.profile import ReadProfileUseCase, UpdateProfileUseCase
from app.application.identity.register import RegisterCustomerUseCase
from app.application.throttle import Throttle
from app.config import Settings, settings
from app.infrastructure.identity_accounts import BcryptPasswordHasher

# The attribute of the application state that holds the origin the account
# links point at. The application factory sets it once.
FRONTEND_ORIGIN_STATE_KEY: Final[str] = "frontend_origin"

_PASSWORD_HASHER = BcryptPasswordHasher()


def account_rules_for(configuration: Settings) -> AccountThrottleRules:
    """Return the seven account rules with the limits a configuration sets."""
    return DEFAULT_ACCOUNT_RULES.with_limits(
        register_per_email=configuration.register_attempts_per_email,
        register_per_address=configuration.register_attempts_per_address,
        verification_per_address=configuration.verification_attempts_per_address,
        resends_per_account=configuration.verification_resends_per_account,
        reset_requests_per_email=configuration.reset_requests_per_email,
        reset_requests_per_address=configuration.reset_requests_per_address,
        reset_completions_per_address=configuration.reset_completions_per_address,
    )


_ACCOUNT_RULES = account_rules_for(settings)


def get_account_rules() -> AccountThrottleRules:
    """Return the account rules, with the limits the process was configured with."""
    return _ACCOUNT_RULES


def get_password_hasher() -> PasswordHasher:
    """Return the bcrypt password hasher. A test overrides this to skip the work factor."""
    return _PASSWORD_HASHER


def get_account_mailer(request: Request, gateway: NotificationGatewayDependency) -> AccountMailer:
    """Return the mailer of the account messages, linked to the configured frontend.

    Raises:
        RuntimeError: If the application carries no frontend origin, which
            means it was assembled some other way than by `create_app`.

    """
    origin = getattr(request.app.state, FRONTEND_ORIGIN_STATE_KEY, None)
    if not isinstance(origin, str) or not origin:
        raise RuntimeError(
            "Attempted to send an account message from an application that was built without "
            f"a frontend origin. Set `app.state.{FRONTEND_ORIGIN_STATE_KEY}` when the "
            "application is assembled, as `create_app` does."
        )
    return AccountMailer(gateway, origin)


ThrottleDependency = Annotated[Throttle, Depends(get_throttle)]
AccountRulesDependency = Annotated[AccountThrottleRules, Depends(get_account_rules)]
PasswordHasherDependency = Annotated[PasswordHasher, Depends(get_password_hasher)]
AccountMailerDependency = Annotated[AccountMailer, Depends(get_account_mailer)]


def get_register_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    passwords: PasswordHasherDependency,
    throttle: ThrottleDependency,
    mailer: AccountMailerDependency,
    rules: AccountRulesDependency,
) -> RegisterCustomerUseCase:
    """Return the registration use case, wired to its collaborators and the limits."""
    return RegisterCustomerUseCase(uow, clock, passwords, throttle, mailer, rules)


def get_verify_email_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    throttle: ThrottleDependency,
    rules: AccountRulesDependency,
) -> VerifyEmailUseCase:
    """Return the use case that redeems a verification token."""
    return VerifyEmailUseCase(uow, clock, throttle, rules)


def get_resend_verification_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    throttle: ThrottleDependency,
    mailer: AccountMailerDependency,
    rules: AccountRulesDependency,
) -> ResendVerificationUseCase:
    """Return the use case that sends an account its verification link again."""
    return ResendVerificationUseCase(uow, clock, throttle, mailer, rules)


def get_request_password_reset_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    throttle: ThrottleDependency,
    mailer: AccountMailerDependency,
    rules: AccountRulesDependency,
) -> RequestPasswordResetUseCase:
    """Return the use case that issues a reset link."""
    return RequestPasswordResetUseCase(uow, clock, throttle, mailer, rules)


def get_complete_password_reset_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    passwords: PasswordHasherDependency,
    throttle: ThrottleDependency,
    rules: AccountRulesDependency,
) -> CompletePasswordResetUseCase:
    """Return the use case that redeems a reset token."""
    return CompletePasswordResetUseCase(uow, clock, passwords, throttle, rules)


def get_read_profile_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> ReadProfileUseCase:
    """Return the use case that reads a customer's own profile."""
    return ReadProfileUseCase(uow, clock)


def get_update_profile_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> UpdateProfileUseCase:
    """Return the use case that edits a customer's own profile."""
    return UpdateProfileUseCase(uow, clock)


RegisterCustomer = Annotated[RegisterCustomerUseCase, Depends(get_register_use_case)]
VerifyEmail = Annotated[VerifyEmailUseCase, Depends(get_verify_email_use_case)]
ResendVerification = Annotated[
    ResendVerificationUseCase, Depends(get_resend_verification_use_case)
]
RequestPasswordReset = Annotated[
    RequestPasswordResetUseCase, Depends(get_request_password_reset_use_case)
]
CompletePasswordReset = Annotated[
    CompletePasswordResetUseCase, Depends(get_complete_password_reset_use_case)
]
ReadProfile = Annotated[ReadProfileUseCase, Depends(get_read_profile_use_case)]
UpdateProfile = Annotated[UpdateProfileUseCase, Depends(get_update_profile_use_case)]
