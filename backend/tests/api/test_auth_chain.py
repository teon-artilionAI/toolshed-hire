"""The HTTP boundary of the layered auth chain.

Authority is read from the database on every request and never from a token
claim. The token does carry the role and the branch, and the dependency chain
does not rely on either, so a role change or a deactivation takes effect on the
very next request rather than whenever the token happens to expire.

These run against the in memory database. What the reservation routes do for a
signed in caller, including the conflict that must be 409 and never 500, is in
tests/api/test_reservation_routes.py and tests/api/test_reservation_refusals.py.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.factories import TEST_PASSWORD, Factory
from tests.support.http import problem_code, problem_of
from tests.support.probe_app import ADMIN_PATH, ANY_ROLE_PATH, COUNTER_PATH
from tests.support.tokens import (
    authorization_header,
    mint_access_token,
    mint_expired_access_token,
    mint_token_signed_with_a_foreign_key,
    tamper_with_signature,
)

ME_PATH: Final[str] = "/api/me"
SIGN_IN_PATH: Final[str] = "/api/auth/login"
AUTHENTICATION_PROBLEM: Final[str] = "authentication-failure"
INVALID_CREDENTIALS_PROBLEM: Final[str] = "invalid-credentials"
AUTHORISATION_PROBLEM: Final[str] = "authorisation-failure"
INACTIVE_PROBLEM: Final[str] = "inactive-account"
# Eleven characters, one short of the policy minimum that used to be enforced on
# the sign in request itself. Wrong either way, and it must be answered the same
# way as any other wrong password.
SHORT_WRONG_PASSWORD: Final[str] = "not-my-pass"
UNKNOWN_EMAIL: Final[str] = "nobody.at.all@toolshedhire.co.za"
# One byte past what bcrypt reads, so the request is refused before hashing.
OVERLONG_PASSWORD_LENGTH: Final[int] = 73
# Every problem document quotes the id of its own request. Two requests that
# are compared whole therefore send the same id, so the only thing left to
# differ is whatever the credential changed.
SHARED_REQUEST_ID: Final[dict[str, str]] = {
    "X-Request-ID": "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
}


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = factory.user(role=UserRole.CUSTOMER)
    session.commit()
    return account


class TestABearerTokenIsRequired:
    """The first layer: no credential means no answer, and never a 500."""

    def test_a_request_with_no_authorization_header_is_refused_with_401(
        self, client: TestClient
    ) -> None:
        response = client.get(ME_PATH)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(response) == AUTHENTICATION_PROBLEM

    def test_a_request_using_a_scheme_other_than_bearer_is_refused_with_401(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        token = mint_access_token(customer.id)
        response = client.get(ME_PATH, headers={"Authorization": f"Basic {token}"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_of(response)["errors"] == {"reason": "unsupported-scheme"}

    def test_a_bearer_header_carrying_no_token_is_refused_with_401(
        self, client: TestClient
    ) -> None:
        response = client.get(ME_PATH, headers={"Authorization": "Bearer "})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_of(response)["errors"] == {"reason": "empty-credentials"}


class TestTokenVerification:
    """The second layer: only a token this server signed, and only while it lives."""

    def test_a_valid_token_reaches_the_endpoint_and_returns_the_signed_in_account(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        response = client.get(ME_PATH, headers=authorization_header(mint_access_token(customer.id)))
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["id"] == str(customer.id)
        assert body["email"] == customer.email
        assert body["role"] == "customer"
        assert body["fullName"] == customer.full_name
        assert body["branchCode"] is None
        assert body["emailVerified"] is False

    def test_an_expired_token_is_refused_with_401(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        expired = mint_expired_access_token(customer.id)
        response = client.get(ME_PATH, headers=authorization_header(expired))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_of(response)["errors"] == {"reason": "expired"}

    def test_a_token_whose_signature_was_edited_is_refused_with_401(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        tampered = tamper_with_signature(mint_access_token(customer.id))
        response = client.get(ME_PATH, headers=authorization_header(tampered))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_of(response)["errors"] == {"reason": "invalid"}

    def test_a_token_signed_with_a_key_this_server_does_not_hold_is_refused_with_401(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        forged = mint_token_signed_with_a_foreign_key(customer.id)
        response = client.get(ME_PATH, headers=authorization_header(forged))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_perfectly_valid_token_naming_no_account_is_refused_with_401(
        self, client: TestClient
    ) -> None:
        response = client.get(ME_PATH, headers=authorization_header(mint_access_token(uuid4())))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_of(response)["errors"] == {"reason": "unknown-subject"}

    def test_a_token_issued_by_the_sign_in_endpoint_is_accepted_by_a_protected_endpoint(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        issued = client.post(
            SIGN_IN_PATH, json={"email": customer.email, "password": TEST_PASSWORD}
        )
        assert issued.status_code == status.HTTP_200_OK
        token = issued.json()["accessToken"]
        response = client.get(ME_PATH, headers=authorization_header(token))
        assert response.status_code == status.HTTP_200_OK


class TestSignInNeverSaysWhichHalfOfTheCredentialWasWrong:
    """Control C-14: an unknown address and a wrong password answer identically.

    The short password is the case that regressed. A minimum length on the sign
    in request turned an eleven character wrong password into a 422 naming the
    length rule, while a twelve character wrong password was a 401. That
    difference is an oracle: it reports something about the value the caller
    just submitted, and it contradicts a control the security section states as
    fact. Length policy belongs to choosing a password, not to presenting one.
    """

    def test_a_wrong_password_shorter_than_the_policy_minimum_is_401_and_not_422(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        response = client.post(
            SIGN_IN_PATH, json={"email": customer.email, "password": SHORT_WRONG_PASSWORD}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(response) == INVALID_CREDENTIALS_PROBLEM

    def test_an_unknown_address_and_a_wrong_password_return_the_same_document(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        wrong_password = client.post(
            SIGN_IN_PATH,
            json={"email": customer.email, "password": SHORT_WRONG_PASSWORD},
            headers=SHARED_REQUEST_ID,
        )
        unknown_account = client.post(
            SIGN_IN_PATH,
            json={"email": UNKNOWN_EMAIL, "password": SHORT_WRONG_PASSWORD},
            headers=SHARED_REQUEST_ID,
        )
        assert wrong_password.status_code == unknown_account.status_code
        assert problem_of(wrong_password) == problem_of(unknown_account)

    def test_a_password_longer_than_bcrypt_can_read_is_still_refused_identically(
        self, client: TestClient, customer: UserAccount
    ) -> None:
        overlong = "x" * OVERLONG_PASSWORD_LENGTH
        wrong_password = client.post(
            SIGN_IN_PATH,
            json={"email": customer.email, "password": overlong},
            headers=SHARED_REQUEST_ID,
        )
        unknown_account = client.post(
            SIGN_IN_PATH,
            json={"email": UNKNOWN_EMAIL, "password": overlong},
            headers=SHARED_REQUEST_ID,
        )
        assert wrong_password.status_code == unknown_account.status_code
        assert problem_of(wrong_password) == problem_of(unknown_account)


class TestRolesAreDatabaseAuthoritative:
    """The third and fourth layers, and why the role claim in the token is not relied on."""

    def test_a_customer_is_refused_by_an_administrator_only_endpoint_with_403(
        self, probe_client: TestClient, customer: UserAccount
    ) -> None:
        response = probe_client.get(
            ADMIN_PATH, headers=authorization_header(mint_access_token(customer.id))
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == AUTHORISATION_PROBLEM
        assert problem_of(response)["errors"] == {"required_roles": ["ADMIN"]}

    def test_an_administrator_reaches_the_administrator_only_endpoint(
        self, probe_client: TestClient, session: Session, factory: Factory
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        response = probe_client.get(
            ADMIN_PATH, headers=authorization_header(mint_access_token(administrator.id))
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == UserRole.ADMIN.value

    def test_counter_staff_reach_an_endpoint_that_admits_counter_staff_and_administrators(
        self, probe_client: TestClient, session: Session, factory: Factory
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        response = probe_client.get(
            COUNTER_PATH, headers=authorization_header(mint_access_token(assistant.id))
        )
        assert response.status_code == status.HTTP_200_OK

    def test_a_role_changed_in_the_database_takes_effect_on_the_next_request(
        self, probe_client: TestClient, session: Session, customer: UserAccount
    ) -> None:
        token = mint_access_token(customer.id)
        headers = authorization_header(token)
        refused = probe_client.get(ADMIN_PATH, headers=headers)
        assert refused.status_code == status.HTTP_403_FORBIDDEN
        customer.role = UserRole.ADMIN
        session.add(customer)
        session.commit()
        assert probe_client.get(ADMIN_PATH, headers=headers).status_code == status.HTTP_200_OK

    def test_an_account_deactivated_after_its_token_was_issued_is_refused(
        self, probe_client: TestClient, session: Session, customer: UserAccount
    ) -> None:
        token = mint_access_token(customer.id)
        headers = authorization_header(token)
        assert probe_client.get(ANY_ROLE_PATH, headers=headers).status_code == status.HTTP_200_OK
        customer.is_active = False
        session.add(customer)
        session.commit()
        response = probe_client.get(ANY_ROLE_PATH, headers=headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == INACTIVE_PROBLEM
        assert problem_of(response)["errors"] == {"reason": "account-deactivated"}
