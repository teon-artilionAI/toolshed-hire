"""The two account paths that choose a password, and a breach service that knows it.

Registration and the completion of a password reset both refuse a password the
service lists. The refusal names the field the request used, so the form can put
the sentence beside the right input. Nothing is written when registration is
refused, and the reset leaves the old password and the sessions alone.
"""

from __future__ import annotations

import pytest

from app.application.identity.account_rules import BREACHED_PASSWORD_MESSAGE
from app.application.refusal import REFUSED_PARAMETER
from app.domain.errors import ValidationFailure
from tests.support.account_desk import (
    NEW_EMAIL,
    RESET_KEY,
    AccountDesk,
    registration,
)
from tests.support.memory_breach import FakeBreachedPasswordChecker


def test_registration_refuses_a_listed_password_and_writes_nothing() -> None:
    """The account is not created and the answer names the password."""
    desk = AccountDesk(breaches=FakeBreachedPasswordChecker(breached=True))
    with pytest.raises(ValidationFailure) as caught:
        desk.register()
    assert caught.value.message == BREACHED_PASSWORD_MESSAGE
    assert caught.value.detail[REFUSED_PARAMETER] == "password"
    assert desk.identity.committed.accounts == {}
    assert desk.breaches.checked == [registration().password]


def test_registration_accepts_a_password_the_service_does_not_list() -> None:
    """The same path creates the account when the answer is no."""
    desk = AccountDesk()
    desk.register()
    assert desk.account_for(NEW_EMAIL).email == NEW_EMAIL
    assert desk.breaches.checked == [registration().password]


def test_a_reset_refuses_a_listed_password_and_keeps_the_old_one() -> None:
    """The reset token is not redeemed and the old password still works."""
    desk = AccountDesk()
    desk.register()
    desk.request_reset(email=NEW_EMAIL)
    token = desk.sent_token(RESET_KEY)
    desk.breaches.breached = True
    with pytest.raises(ValidationFailure) as caught:
        desk.complete_reset(token)
    assert caught.value.message == BREACHED_PASSWORD_MESSAGE
    assert caught.value.detail[REFUSED_PARAMETER] == "newPassword"
    assert desk.hasher.call_count == 1
