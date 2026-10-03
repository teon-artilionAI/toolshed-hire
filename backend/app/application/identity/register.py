"""The use case that registers a new customer (FR-01, US-01, BR-45, R-13).

A person who registers gets a sign in account with the customer role, a
customer profile at the branch they chose and a message with a link that
proves their email address. The account and the profile are written in one
transaction, with the audit event, so there is never one without the other.

The answer never says whether the address already had an account (C-14). An
address that has one gets no new account and nothing about the old one
changes. Its holder is sent a short note saying somebody tried to register
with it, and that note carries no token.

The work is the same on both paths as well, so the time the answer takes
gives nothing away. The fields are checked first, a password is hashed and a
token is minted whether or not the address is free, one audit event is
written and one message is sent. What differs is two inserts, which is a
matter of a millisecond beside a hash that takes a quarter of a second.

The password is hashed before the transaction opens, so no row is held while
the work factor runs. It is never logged and never returned.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.identity.account_mail import AccountMailer, MailExpectation
from app.application.identity.account_rules import (
    ensure_password_may_be_set,
    normalised_email,
    refused_field,
)
from app.application.identity.attempts import (
    DEFAULT_ACCOUNT_RULES,
    AccountThrottleRules,
    address_subject,
    count_attempt,
)
from app.application.identity.ports import EmailAlreadyRegistered, PasswordHasher
from app.application.identity.sessions import ACCOUNT_ENTITY_TYPE, ClientDetails
from app.application.refusal import refused
from app.application.throttle import Throttle
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.account import Account
from app.domain.account_tokens import PendingToken, mint_account_token
from app.domain.customer_account import NewCustomer
from app.domain.enums import IdDocType
from app.domain.errors import ValidationFailure

logger = logging.getLogger(__name__)

REGISTERED_ACTION: Final[str] = "auth.registered"
REGISTRATION_REPEATED_ACTION: Final[str] = "auth.registration_repeated"
PASSWORD_PARAMETER: Final[str] = "password"
HOME_BRANCH_PARAMETER: Final[str] = "homeBranchCode"
PRIVACY_NOTICE_PARAMETER: Final[str] = "acceptsPrivacyNotice"
UNKNOWN_BRANCH_MESSAGE: Final[str] = "Choose one of our branches."
PRIVACY_NOTICE_MESSAGE: Final[str] = "Please accept the privacy notice to register."
CREATED_OUTCOME: Final[str] = "created"
ALREADY_REGISTERED_OUTCOME: Final[str] = "already-registered"


@dataclass(frozen=True, slots=True)
class RegisterCustomerCommand:
    """A request to open a customer account.

    Attributes:
        email: The address as it was typed.
        password: The password as it was typed. Kept out of the representation.
        full_name: The name of the person registering.
        phone: The number the branch can reach them on.
        id_document_type: The kind of identity document they will present.
        id_document_last4: Its last four characters.
        billing_address_line1: The first line of the billing address.
        billing_suburb: The suburb.
        billing_city: The city.
        billing_postal_code: The postal code.
        home_branch_code: The code of the branch they register at.
        accepts_privacy_notice: Whether they accepted the privacy notice.
        client: Where the request came from.

    """

    email: str
    password: str = field(repr=False)
    full_name: str
    phone: str
    id_document_type: IdDocType
    id_document_last4: str
    billing_address_line1: str
    billing_suburb: str
    billing_city: str
    billing_postal_code: str
    home_branch_code: str
    accepts_privacy_notice: bool
    client: ClientDetails = field(default_factory=ClientDetails)


class RegisterCustomerUseCase(UseCase[RegisterCustomerCommand, MailExpectation]):
    """Open a customer account, or answer in the same way when the address has one."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        passwords: PasswordHasher,
        throttle: Throttle,
        mailer: AccountMailer,
        rules: AccountThrottleRules = DEFAULT_ACCOUNT_RULES,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            passwords: Hashes the chosen password.
            throttle: Counts the attempt for the address and for the client.
            mailer: Sends the message once the transaction has committed.
            rules: The limits of the windows. The defaults when omitted.

        """
        super().__init__(uow, clock)
        self._passwords = passwords
        self._throttle = throttle
        self._mailer = mailer
        self._rules = rules

    def execute(self, command: RegisterCustomerCommand) -> MailExpectation:
        """Register the person, and send the message their address is owed.

        Returns:
            Whether a message for the address would be delivered here. It is
            the same whether or not the address already had an account.

        Raises:
            TooManyAttempts: If the address or the client went over its window.
            ValidationFailure: If a field is refused. The detail names it.

        """
        now = self._clock.now()
        email = normalised_email(command.email)
        logger.info(
            "auth.register_started",
            extra={"client_address_known": command.client.address is not None},
        )
        counted = (
            (self._rules.register_email, email),
            (self._rules.register_address, address_subject(command.client)),
        )
        count_attempt(self._uow, self._throttle, counted, now)
        customer = _checked_customer(command)
        # One hash and one token on every path, whether or not the address is free.
        account = Account.registered_customer(
            email=email,
            password_hash=self._passwords.hash(command.password),
            full_name=customer.full_name,
            phone=customer.phone,
        )
        token = mint_account_token()
        account.start_email_verification(PendingToken.for_email_verification(token, now))
        try:
            with self._uow as uow:
                created = self._register(uow, command, account, customer, now)
                uow.commit()
        except EmailAlreadyRegistered:
            # Another registration took the address between the lookup and the
            # write. The unit of work has rolled back, and the caller is
            # answered as for any address that already has an account.
            logger.warning("auth.register_lost_the_address")
            created = False
        if created:
            self._mailer.send_verification(to=email, token=token)
        else:
            self._mailer.send_already_registered(to=email)
        logger.info(
            "auth.register_finished",
            extra={"outcome": CREATED_OUTCOME if created else ALREADY_REGISTERED_OUTCOME},
        )
        return self._mailer.expectation_for(email)

    def _register(
        self,
        uow: UnitOfWork,
        command: RegisterCustomerCommand,
        account: Account,
        customer: NewCustomer,
        now: datetime,
    ) -> bool:
        """Write the account and its profile, or note the repeat. Nothing is committed here.

        Returns:
            True when the account was written, False when its address had one.

        """
        branch_code = command.home_branch_code.strip()
        branch = uow.branches.find_active_by_code(branch_code)
        if branch is None:
            raise refused(HOME_BRANCH_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
        existing = uow.accounts.find_by_email_for_update(account.email)
        if existing is not None:
            uow.audit.record(
                audit_event_for(
                    actor=None,
                    entity_type=ACCOUNT_ENTITY_TYPE,
                    entity_id=existing.id,
                    action=REGISTRATION_REPEATED_ACTION,
                    occurred_at=now,
                    after_state={"account_created": False},
                )
            )
            return False
        uow.accounts.add(account)
        profile_id = uow.customers.add_registered(
            user_account_id=account.id, registered_branch_id=branch.id, customer=customer
        )
        uow.audit.record(
            audit_event_for(
                actor=account.as_actor(),
                entity_type=ACCOUNT_ENTITY_TYPE,
                entity_id=account.id,
                action=REGISTERED_ACTION,
                occurred_at=now,
                after_state={
                    "role": account.role.value,
                    "customer_profile_id": str(profile_id),
                    "home_branch_code": branch.code,
                    "email_verified": False,
                },
            )
        )
        logger.info(
            "auth.register_written",
            extra={"user_id": str(account.id), "customer_profile_id": str(profile_id)},
        )
        return True


def _checked_customer(command: RegisterCustomerCommand) -> NewCustomer:
    """Return the details of the person registering, or refuse the field that is wrong."""
    if not command.accepts_privacy_notice:
        raise refused(PRIVACY_NOTICE_PARAMETER, PRIVACY_NOTICE_MESSAGE)
    ensure_password_may_be_set(command.password, PASSWORD_PARAMETER)
    try:
        return NewCustomer.registering(
            full_name=command.full_name,
            phone=command.phone,
            id_document_type=command.id_document_type,
            id_document_last4=command.id_document_last4,
            billing_address_line1=command.billing_address_line1,
            billing_suburb=command.billing_suburb,
            billing_city=command.billing_city,
            billing_postal_code=command.billing_postal_code,
        )
    except ValidationFailure as failure:
        raise refused_field(failure) from failure

