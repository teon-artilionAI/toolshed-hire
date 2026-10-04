"""The use case by which an administrator opens a staff account (FR-25, US-35).

Opening an account writes a `user_account` with the role and the branch the
administrator chose, a password hash of a random value nobody kept, and a
reset token. The person is sent the reset link every account uses, and
chooses their own password through the reset flow, so no administrator ever
reads or sets one. The random value is hashed before the transaction opens,
so no row is held while the work factor runs. The answer says whether the
email gateway took the message, because an administrator who hears it did not
can tell the person to ask for a new link once mail reaches them.

An address another account holds is refused naming `email`, whether the
lookup finds it or the unique constraint does when two administrators race.
An edit of an account is in `staff_edit`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

from app.application.catalogue.catalogue_changes import checked
from app.application.clock import Clock
from app.application.identity.account_mail import AccountMailer
from app.application.identity.account_rules import normalised_email, wire_name
from app.application.identity.ports import EmailAlreadyRegistered, PasswordHasher
from app.application.identity.staff_changes import (
    ACTIVE_KEY,
    BRANCH_KEY,
    ROLE_KEY,
    STAFF_OPENED_ACTION,
    StaffAccountUseCase,
    locked_administrators,
    record_staff_change,
    trading_branch_id,
)
from app.application.identity.staff_commands import OpenStaffAccountCommand, StaffAccountOpened
from app.application.identity.staff_read_models import StaffDirectory
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.domain.account import Account
from app.domain.account_tokens import PendingToken, mint_account_token
from app.domain.staff_account import (
    EMAIL,
    StaffDetails,
    checked_staff_details,
    new_staff_account,
)

logger = logging.getLogger(__name__)

EMAIL_TAKEN_MESSAGE: Final[str] = "Another account already uses this email address."
RESET_LINK_KEY: Final[str] = "reset_link_issued"


class OpenStaffAccountUseCase(StaffAccountUseCase[OpenStaffAccountCommand, StaffAccountOpened]):
    """Open a staff account with a reset link, and record it."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        directory: StaffDirectory,
        passwords: PasswordHasher,
        mailer: AccountMailer,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            directory: The read the answer comes from.
            passwords: Hashes the random value the account is opened with.
            mailer: Sends the reset link once the transaction has committed.

        """
        super().__init__(uow, clock, directory)
        self._passwords = passwords
        self._mailer = mailer

    def execute(self, command: OpenStaffAccountCommand) -> StaffAccountOpened:
        """Open the account, send its reset link and say whether the link went.

        Raises:
            ValidationFailure: Naming the field, for a name, a phone, a role or
                a branch that breaks a rule, or an address another account holds.
            AuthorisationFailure: If the actor is no longer an active administrator.

        """
        logger.info(
            "staff.open_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "role": command.role.value,
                "branch_code": command.branch_code,
            },
        )
        email = normalised_email(command.email)
        has_branch = command.branch_code is not None
        details = checked(
            lambda given: checked_staff_details(given, has_branch=has_branch),
            StaffDetails(full_name=command.full_name, phone=command.phone, role=command.role),
        )
        # A value nobody keeps, so no password opens the account until the
        # person chooses one through the link.
        unusable_hash = self._passwords.hash(mint_account_token())
        token = mint_account_token()
        now = self._clock.now()
        with self._uow as uow:
            locked_administrators(uow, command.actor)
            account = self._new_account(uow, command, email, details, unusable_hash, token, now)
            record_staff_change(
                uow,
                actor=command.actor,
                account_id=account.id,
                action=STAFF_OPENED_ACTION,
                now=now,
                before=None,
                after={
                    ROLE_KEY: account.role.value,
                    BRANCH_KEY: command.branch_code,
                    ACTIVE_KEY: True,
                    RESET_LINK_KEY: True,
                },
            )
            uow.commit()
        delivered = self._mailer.send_staff_invitation(to=email, token=token)
        logger.info(
            "staff.opened",
            extra={"user_id": str(account.id), "role": account.role.value, "delivered": delivered},
        )
        return StaffAccountOpened(member=self._answer(account.id), email_deliverable=delivered)

    @staticmethod
    def _new_account(
        uow: UnitOfWork,
        command: OpenStaffAccountCommand,
        email: str,
        details: StaffDetails,
        unusable_hash: str,
        token: str,
        now: datetime,
    ) -> Account:
        """Write the new account, or refuse an address or a branch it cannot have.

        Raises:
            ValidationFailure: Naming `email` or `branchCode`.

        """
        if uow.accounts.find_by_email_for_update(email) is not None:
            logger.info("staff.email_taken", extra={"found_by": "lookup"})
            raise refused(wire_name(EMAIL), EMAIL_TAKEN_MESSAGE)
        branch_id = (
            trading_branch_id(uow, command.branch_code) if command.branch_code is not None else None
        )
        account = new_staff_account(
            email=email,
            unusable_password_hash=unusable_hash,
            details=details,
            branch_id=branch_id,
            reset=PendingToken.for_password_reset(token, now),
        )
        try:
            uow.accounts.add(account)
        except EmailAlreadyRegistered as taken:
            logger.warning("staff.email_taken", extra={"found_by": "unique-constraint"})
            raise refused(wire_name(EMAIL), EMAIL_TAKEN_MESSAGE) from taken
        return account


__all__ = ["EMAIL_TAKEN_MESSAGE", "OpenStaffAccountUseCase"]
