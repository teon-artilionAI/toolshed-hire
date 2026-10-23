"""The breach check on the two routes that choose a password (R-14, C-18).

Registration and the completion of a password reset refuse a password the
service lists. The refusal is a 422 with the sentence beside the password
field, and nothing is written. The routes are exercised through the real
application with the checker replaced, so no test depends on a third party.
"""

from __future__ import annotations

from typing import Final

from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.api.account_deps import get_breached_password_checker
from app.application.identity.account_rules import BREACHED_PASSWORD_MESSAGE
from app.infrastructure.models import UserAccount
from app.infrastructure.security import verify_password
from app.main import app as production_app
from tests.support.account_desk import RESET_KEY
from tests.support.accounts_api import (
    NEW_EMAIL,
    REGISTER_PATH,
    RESET_COMPLETE_PATH,
    RESET_REQUEST_PATH,
    registration_body,
    token_from,
)
from tests.support.http import problem_code, problem_of
from tests.support.memory_breach import FakeBreachedPasswordChecker

PASSWORD_FIELD: Final[str] = "body.password"
NEW_PASSWORD_FIELD: Final[str] = "body.newPassword"


def test_registration_refuses_a_password_the_service_lists(
    account_api: TestClient, session: Session
) -> None:
    """The account is not created and the message sits under the password field."""
    production_app.dependency_overrides[get_breached_password_checker] = (
        lambda: FakeBreachedPasswordChecker(breached=True)
    )
    try:
        response = account_api.post(REGISTER_PATH, json=registration_body())
    finally:
        production_app.dependency_overrides.pop(get_breached_password_checker, None)

    assert response.status_code == 422
    assert problem_code(response) == "request-validation-failure"
    fields = problem_of(response)["errors"]["fields"]
    assert fields[PASSWORD_FIELD] == BREACHED_PASSWORD_MESSAGE
    session.expire_all()
    assert session.exec(
        select(UserAccount).where(col(UserAccount.email) == NEW_EMAIL)
    ).first() is None


def test_a_reset_refuses_a_password_the_service_lists(
    account_api: TestClient, email_gateway, session: Session, home_branch
) -> None:
    """The reset token is not redeemed and the old password stays."""
    assert account_api.post(REGISTER_PATH, json=registration_body()).status_code == 202
    assert account_api.post(
        RESET_REQUEST_PATH, json={"email": NEW_EMAIL}
    ).status_code == 202
    token = token_from(email_gateway, NEW_EMAIL, RESET_KEY)
    production_app.dependency_overrides[get_breached_password_checker] = (
        lambda: FakeBreachedPasswordChecker(breached=True)
    )
    try:
        response = account_api.post(
            RESET_COMPLETE_PATH,
            json={"token": token, "newPassword": "another-made-up-passphrase"},
        )
    finally:
        production_app.dependency_overrides.pop(get_breached_password_checker, None)

    assert response.status_code == 422
    fields = problem_of(response)["errors"]["fields"]
    assert fields[NEW_PASSWORD_FIELD] == BREACHED_PASSWORD_MESSAGE
    session.expire_all()
    account = session.exec(
        select(UserAccount).where(col(UserAccount.email) == NEW_EMAIL)
    ).one()
    assert verify_password("a-made-up-passphrase-for-tests", account.password_hash)
