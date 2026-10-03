"""The account use cases, wired over the in memory stores for a unit test.

`AccountDesk` is the `Desk` of the session tests with the things the account
use cases add. It holds a fake email gateway that keeps what it was asked to
send, a password hasher that counts, the throttle rules and the origin the
links point at, and it wires each use case the way the composition root does,
with a unit of work of its own over the same stores.

A test reads a token the way a person does, out of the link in the message
that was sent. `token_in` does that, so no test reaches into a use case for a
value the use case never hands back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final
from uuid import UUID, uuid4

from app.application.identity.account_mail import AccountMailer, MailExpectation
from app.application.identity.attempts import DEFAULT_ACCOUNT_RULES, AccountThrottleRules
from app.application.identity.email_verification import (
    ResendVerificationCommand,
    ResendVerificationUseCase,
    VerifyEmailCommand,
    VerifyEmailUseCase,
)
from app.application.identity.password_reset import (
    CompletePasswordResetCommand,
    CompletePasswordResetUseCase,
    RequestPasswordResetCommand,
    RequestPasswordResetUseCase,
)
from app.application.identity.profile import (
    ReadProfileQuery,
    ReadProfileUseCase,
    UpdateProfileCommand,
    UpdateProfileUseCase,
)
from app.application.identity.register import RegisterCustomerCommand, RegisterCustomerUseCase
from app.application.identity.sessions import ClientDetails
from app.application.notification.ports import NotificationGateway
from app.domain.account import Account
from app.domain.customer_account import CustomerDetails
from app.domain.enums import IdDocType, UserRole
from app.domain.identity import Actor, Branch
from app.domain.notification import EmailMessage
from app.infrastructure.notification import FakeEmailGateway
from tests.support.factories import CLOSES_AT
from tests.support.identity_desk import CLIENT, Desk
from tests.support.memory_crypto import CountingPasswordHasher
from tests.support.memory_identity import KNOWN_EMAIL

FRONTEND_ORIGIN: Final[str] = "https://toolshed-hire.example.test"
NEW_EMAIL: Final[str] = "thandi.mokoena@example.co.za"
CHOSEN_PASSWORD: Final[str] = "a-made-up-passphrase-for-tests"
NEW_PASSWORD: Final[str] = "another-made-up-passphrase"
HOME_BRANCH_CODE: Final[str] = "CBD"
VERIFY_KEY: Final[str] = "verify"
RESET_KEY: Final[str] = "reset"
_TOKEN_IN_LINK: Final[str] = r"#{key}=([A-Za-z0-9_-]+)"


def token_in(message: EmailMessage, key: str) -> str:
    """Return the token a message carries in the fragment of its link.

    Raises:
        AssertionError: If the message carries no link of that kind.

    """
    found = re.search(_TOKEN_IN_LINK.format(key=key), message.text_body)
    assert found is not None, f"The message carries no link with a `{key}` token."
    return found.group(1)


def registration(**overrides: object) -> RegisterCustomerCommand:
    """Return a registration command that is accepted, with any field replaced."""
    values: dict[str, object] = {
        "email": NEW_EMAIL,
        "password": CHOSEN_PASSWORD,
        "full_name": "Thandi Mokoena",
        "phone": "082 441 7719",
        "id_document_type": IdDocType.SA_ID,
        "id_document_last4": "5083",
        "billing_address_line1": "12 Loop Street",
        "billing_suburb": "Gardens",
        "billing_city": "Cape Town",
        "billing_postal_code": "8001",
        "home_branch_code": HOME_BRANCH_CODE,
        "accepts_privacy_notice": True,
        "client": CLIENT,
        **overrides,
    }
    return RegisterCustomerCommand(**values)


@dataclass
class AccountDesk(Desk):
    """Everything one account test needs, wired the way the composition root wires it."""

    gateway: FakeEmailGateway = field(default_factory=FakeEmailGateway)
    gateway_override: NotificationGateway | None = None
    hasher: CountingPasswordHasher = field(default_factory=CountingPasswordHasher)
    account_rules: AccountThrottleRules = DEFAULT_ACCOUNT_RULES
    branch: Branch = field(
        default_factory=lambda: Branch(
            id=uuid4(), code=HOME_BRANCH_CODE, name="Cape Town CBD", closes_at=CLOSES_AT
        )
    )

    def __post_init__(self) -> None:
        """Open the one branch a customer can register at."""
        self.store.branches[self.branch.id] = self.branch

    def mailer(self) -> AccountMailer:
        """Return the mailer of the account messages, over the fake gateway by default."""
        return AccountMailer(self.gateway_override or self.gateway, FRONTEND_ORIGIN)

    def register(self, **overrides: object) -> MailExpectation:
        """Run the registration use case once, with any field of the command replaced."""
        use_case = RegisterCustomerUseCase(
            self._uow(), self.clock, self.hasher, self.throttle, self.mailer(), self.account_rules
        )
        return use_case.execute(registration(**overrides))

    def verify(self, token: str, client: ClientDetails = CLIENT) -> None:
        """Run the use case that redeems a verification token."""
        use_case = VerifyEmailUseCase(self._uow(), self.clock, self.throttle, self.account_rules)
        use_case.execute(VerifyEmailCommand(token=token, client=client))

    def resend(self, account_id: UUID, role: UserRole = UserRole.CUSTOMER) -> MailExpectation:
        """Run the use case that sends an account its verification link again."""
        use_case = ResendVerificationUseCase(
            self._uow(), self.clock, self.throttle, self.mailer(), self.account_rules
        )
        return use_case.execute(
            ResendVerificationCommand(actor=Actor(user_id=account_id, role=role))
        )

    def request_reset(
        self, email: str = KNOWN_EMAIL, client: ClientDetails = CLIENT
    ) -> MailExpectation:
        """Run the use case that issues a reset link."""
        use_case = RequestPasswordResetUseCase(
            self._uow(), self.clock, self.throttle, self.mailer(), self.account_rules
        )
        return use_case.execute(RequestPasswordResetCommand(email=email, client=client))

    def complete_reset(
        self, token: str, new_password: str = NEW_PASSWORD, client: ClientDetails = CLIENT
    ) -> None:
        """Run the use case that redeems a reset token."""
        use_case = CompletePasswordResetUseCase(
            self._uow(), self.clock, self.hasher, self.throttle, self.account_rules
        )
        use_case.execute(
            CompletePasswordResetCommand(token=token, new_password=new_password, client=client)
        )

    def read_profile(self, account_id: UUID) -> CustomerDetails:
        """Run the use case that reads a customer's own profile."""
        actor = Actor(user_id=account_id, role=UserRole.CUSTOMER)
        return ReadProfileUseCase(self._uow(), self.clock).execute(ReadProfileQuery(actor=actor))

    def update_profile(self, account_id: UUID, **changes: str | None) -> CustomerDetails:
        """Run the use case that edits a customer's own profile."""
        actor = Actor(user_id=account_id, role=UserRole.CUSTOMER)
        return UpdateProfileUseCase(self._uow(), self.clock).execute(
            UpdateProfileCommand(actor=actor, changes=changes)
        )

    def account_for(self, email: str = NEW_EMAIL) -> Account:
        """Return the committed account with this address.

        Raises:
            LookupError: If no account with this address was committed.

        """
        for account in self.identity.committed.accounts.values():
            if account.email == email:
                return account
        raise LookupError(f"No committed account has the address {email}.")

    def sent_token(self, key: str) -> str:
        """Return the token in the link of the last message the gateway was handed."""
        return token_in(self.gateway.sent[-1], key)

    def registered(self) -> Account:
        """Register the new customer and return their committed account."""
        self.register()
        return self.account_for()


__all__ = [
    "CHOSEN_PASSWORD",
    "FRONTEND_ORIGIN",
    "HOME_BRANCH_CODE",
    "NEW_EMAIL",
    "NEW_PASSWORD",
    "RESET_KEY",
    "VERIFY_KEY",
    "AccountDesk",
    "registration",
    "token_in",
]
