"""The use cases by which an administrator deactivates a staff account and reactivates it (US-35).

Deactivating an account stops it at once. Every request reads the account and
refuses one that is not active, so a token issued before the change stops
working on its next request, and signing in refuses it in the words a wrong
password gets. In the same transaction every refresh session of the account
is revoked with the reason `ADMIN_REVOKE`, so no browser can be handed a new
token either, and a reset link still pending stops working, so nobody can
choose the password a reactivation would bring back. The reason the
administrator gave is kept in the audit event.
Nothing is deleted (BR-51), so everything the account ever did stays in the
records and in the audit log.

The last active administrator is never deactivated, and an administrator
cannot deactivate their own account. Both are a 409 and change nothing.

Reactivating an account lets the person sign in again with the password they
already had. Nobody sets one for them.

Asking for the state an account is already in writes nothing.
"""

from __future__ import annotations

import logging
from typing import Final

from app.application.identity.account_rules import refused_field
from app.application.identity.staff_changes import (
    ACTIVE_KEY,
    STAFF_DEACTIVATED_ACTION,
    STAFF_REACTIVATED_ACTION,
    StaffAccountUseCase,
    locked_administrators,
    locked_staff_account,
    record_staff_change,
)
from app.application.identity.staff_commands import (
    DeactivateStaffAccountCommand,
    ReactivateStaffAccountCommand,
)
from app.application.identity.staff_read_models import StaffMember
from app.domain.enums import RevokeReason
from app.domain.errors import ValidationFailure
from app.domain.override_reason import written_reason
from app.domain.staff_account import (
    deactivated,
    ensure_an_administrator_remains,
    ensure_not_own_account,
    reactivated,
)

logger = logging.getLogger(__name__)

# The reason the schema gives a session an administrator ended (BR-48).
DEACTIVATION_REVOKE_REASON: Final[RevokeReason] = RevokeReason.ADMIN_REVOKE
REASON_KEY: Final[str] = "reason"
REVOKED_COUNT_KEY: Final[str] = "revoked_session_count"
REVOKE_REASON_KEY: Final[str] = "revoke_reason"
RESET_WITHDRAWN_KEY: Final[str] = "reset_link_withdrawn"


class DeactivateStaffAccountUseCase(
    StaffAccountUseCase[DeactivateStaffAccountCommand, StaffMember]
):
    """Stop an account signing in and revoke every session it holds, in one transaction."""

    def execute(self, command: DeactivateStaffAccountCommand) -> StaffMember:
        """Deactivate the account, or refuse and change nothing.

        Raises:
            ValidationFailure: Naming `reason`, when it is out of bounds.
            NotFound: If no staff account has the key.
            StateTransitionError: If it is the actor's own account, or the
                last active administrator.
            AuthorisationFailure: If the actor is no longer an active administrator.

        """
        logger.info(
            "staff.deactivation_requested",
            extra={"actor_user_id": str(command.actor.user_id), "user_id": str(command.user_id)},
        )
        try:
            reason = written_reason(command.reason)
        except ValidationFailure as failure:
            raise refused_field(failure) from failure
        now = self._clock.now()
        with self._uow as uow:
            administrators = locked_administrators(uow, command.actor)
            account = locked_staff_account(uow, command.user_id)
            ensure_not_own_account(command.actor.user_id, account.id)
            if not account.is_active:
                logger.info("staff.deactivation_unchanged", extra={"user_id": str(account.id)})
                return self._answer(account.id)
            stopped = deactivated(account)
            ensure_an_administrator_remains(
                account, after=stopped, active_administrators=administrators
            )
            uow.staff.save_staff(stopped)
            reset_withdrawn = account.password_reset is not None
            if reset_withdrawn:
                uow.accounts.save_security_state(stopped)
            revoked = uow.sessions.revoke_all_for_account(
                user_account_id=account.id, reason=DEACTIVATION_REVOKE_REASON, at=now
            )
            record_staff_change(
                uow,
                actor=command.actor,
                account_id=account.id,
                action=STAFF_DEACTIVATED_ACTION,
                now=now,
                before={ACTIVE_KEY: True},
                after={
                    ACTIVE_KEY: False,
                    REASON_KEY: reason,
                    REVOKED_COUNT_KEY: revoked,
                    REVOKE_REASON_KEY: DEACTIVATION_REVOKE_REASON.value,
                    RESET_WITHDRAWN_KEY: reset_withdrawn,
                },
            )
            uow.commit()
        logger.info(
            "staff.deactivated",
            extra={"user_id": str(account.id), "revoked_session_count": revoked},
        )
        return self._answer(account.id)


class ReactivateStaffAccountUseCase(
    StaffAccountUseCase[ReactivateStaffAccountCommand, StaffMember]
):
    """Let a deactivated account sign in again, with the password it already had."""

    def execute(self, command: ReactivateStaffAccountCommand) -> StaffMember:
        """Reactivate the account, or answer it as it stands when it is already active.

        Raises:
            NotFound: If no staff account has the key.
            AuthorisationFailure: If the actor is no longer an active administrator.

        """
        logger.info(
            "staff.reactivation_requested",
            extra={"actor_user_id": str(command.actor.user_id), "user_id": str(command.user_id)},
        )
        now = self._clock.now()
        with self._uow as uow:
            locked_administrators(uow, command.actor)
            account = locked_staff_account(uow, command.user_id)
            if account.is_active:
                logger.info("staff.reactivation_unchanged", extra={"user_id": str(account.id)})
                return self._answer(account.id)
            uow.staff.save_staff(reactivated(account))
            record_staff_change(
                uow,
                actor=command.actor,
                account_id=account.id,
                action=STAFF_REACTIVATED_ACTION,
                now=now,
                before={ACTIVE_KEY: False},
                after={ACTIVE_KEY: True},
            )
            uow.commit()
        logger.info("staff.reactivated", extra={"user_id": str(account.id)})
        return self._answer(account.id)
