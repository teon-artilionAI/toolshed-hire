"""The five account endpoints, which are registration, verification and the password reset.

`POST /api/auth/register` and `POST /api/auth/password-reset/request` are
public and answer 202 with the same body whether or not the address has an
account. The body says one thing, which is whether a message for that address
would be delivered in this environment at all. That depends on how the email
gateway is configured and on the address, and on nothing else (C-14).

`POST /api/auth/email-verification` and `POST /api/auth/password-reset/complete`
are public and take the token of a link. A token that is unknown, already used
or out of time is answered 400, in one sentence for all three.

`POST /api/auth/email-verification/resend` is for any signed in account. It
answers 202 and does nothing for an account that is already verified.

Every one of them is throttled, and a caller who has tried too often gets a
429 with `Retry-After`. No response here is stored by any cache.

The routers do no work of their own beyond the HTTP boundary. Each hands a
command to a use case that arrives already wired, and shapes what comes back.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.api.account_deps import (
    CompletePasswordReset,
    RegisterCustomer,
    RequestPasswordReset,
    ResendVerification,
    VerifyEmail,
)
from app.api.account_schemas import (
    LINK_INVALID_RESPONSE,
    REFUSED_BODY_RESPONSE,
    TOO_MANY_ATTEMPTS_RESPONSE,
    EmailDeliverableResponse,
    PasswordResetCompletionRequest,
    PasswordResetRequest,
    RegisterRequest,
    TokenRequest,
)
from app.api.booking_deps import actor_of
from app.api.deps import AnyRoleUser, public_access
from app.api.identity_deps import ClientDetailsDependency, never_store
from app.application.identity.email_verification import (
    ResendVerificationCommand,
    VerifyEmailCommand,
)
from app.application.identity.password_reset import (
    CompletePasswordResetCommand,
    RequestPasswordResetCommand,
)
from app.application.identity.register import RegisterCustomerCommand

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(never_store)])

THROTTLED: dict[int | str, dict[str, object]] = {
    status.HTTP_429_TOO_MANY_REQUESTS: TOO_MANY_ATTEMPTS_RESPONSE,
}
REFUSED_OR_THROTTLED: dict[int | str, dict[str, object]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    **THROTTLED,
}
LINK_REFUSALS: dict[int | str, dict[str, object]] = {
    status.HTTP_400_BAD_REQUEST: LINK_INVALID_RESPONSE,
    **REFUSED_OR_THROTTLED,
}


@router.post(
    "/register",
    response_model=EmailDeliverableResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a customer account and send the verification link",
    dependencies=[Depends(public_access)],
    responses=REFUSED_OR_THROTTLED,
)
def post_register(
    payload: RegisterRequest, use_case: RegisterCustomer, client: ClientDetailsDependency
) -> EmailDeliverableResponse:
    """Open a customer account, or answer in the same way when the address has one.

    Raises:
        ValidationFailure: If a field is refused. HTTP 422, naming the field.
        TooManyAttempts: If the caller is throttled. HTTP 429.

    """
    expectation = use_case.execute(
        RegisterCustomerCommand(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            phone=payload.phone,
            id_document_type=payload.id_document_type,
            id_document_last4=payload.id_document_last4,
            billing_address_line1=payload.billing_address_line1,
            billing_suburb=payload.billing_suburb,
            billing_city=payload.billing_city,
            billing_postal_code=payload.billing_postal_code,
            home_branch_code=payload.home_branch_code,
            accepts_privacy_notice=payload.accepts_privacy_notice,
            client=client,
        )
    )
    return EmailDeliverableResponse(email_deliverable=expectation.email_deliverable)


@router.post(
    "/email-verification",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Prove an email address with the token of a verification link",
    dependencies=[Depends(public_access)],
    responses=LINK_REFUSALS,
)
def post_email_verification(
    payload: TokenRequest, use_case: VerifyEmail, client: ClientDetailsDependency
) -> None:
    """Redeem a verification token. It works once.

    Raises:
        VerificationLinkInvalid: If the token is unknown, used or out of
            time. HTTP 400.
        TooManyAttempts: If the caller is throttled. HTTP 429.

    """
    use_case.execute(VerifyEmailCommand(token=payload.token, client=client))


@router.post(
    "/email-verification/resend",
    response_model=EmailDeliverableResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send the signed in account its verification link again",
    responses=THROTTLED,
)
def post_verification_resend(
    user: AnyRoleUser, use_case: ResendVerification
) -> EmailDeliverableResponse:
    """Issue a new verification link, or do nothing for a verified account.

    Raises:
        TooManyAttempts: If the account is throttled. HTTP 429.

    """
    expectation = use_case.execute(ResendVerificationCommand(actor=actor_of(user)))
    return EmailDeliverableResponse(email_deliverable=expectation.email_deliverable)


@router.post(
    "/password-reset/request",
    response_model=EmailDeliverableResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask for a password reset link",
    dependencies=[Depends(public_access)],
    responses=REFUSED_OR_THROTTLED,
)
def post_password_reset_request(
    payload: PasswordResetRequest, use_case: RequestPasswordReset, client: ClientDetailsDependency
) -> EmailDeliverableResponse:
    """Send a reset link to an address that has an account, and say nothing either way.

    Raises:
        TooManyAttempts: If the caller is throttled. HTTP 429.

    """
    expectation = use_case.execute(
        RequestPasswordResetCommand(email=payload.email, client=client)
    )
    return EmailDeliverableResponse(email_deliverable=expectation.email_deliverable)


@router.post(
    "/password-reset/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Choose a new password with the token of a reset link",
    dependencies=[Depends(public_access)],
    responses=LINK_REFUSALS,
)
def post_password_reset_completion(
    payload: PasswordResetCompletionRequest,
    use_case: CompletePasswordReset,
    client: ClientDetailsDependency,
) -> None:
    """Set the new password, end every session of the account and lift any lock.

    Raises:
        ResetLinkInvalid: If the token is unknown, used or out of time. HTTP 400.
        ValidationFailure: If the new password is refused. HTTP 422.
        TooManyAttempts: If the caller is throttled. HTTP 429.

    """
    use_case.execute(
        CompletePasswordResetCommand(
            token=payload.token, new_password=payload.new_password, client=client
        )
    )
