"""The security headers on every response (C-06 to C-12).

Every response is checked, including the ones nobody planned for. A header
that is present on a 200 and missing from a 500 protects the responses that
needed it least, so the errors are tested as carefully as the successes.

Two headers depend on something. `Strict-Transport-Security` is sent in staging
and production and nowhere else. `Cache-Control: no-store` is sent whenever the
request carried a credential, whether or not the credential was any good.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.security_headers import (
    CACHE_CONTROL_HEADER,
    CACHE_CONTROL_NO_STORE_VALUE,
    CONTENT_SECURITY_POLICY_HEADER,
    CONTENT_SECURITY_POLICY_VALUE,
    CONTENT_TYPE_OPTIONS_HEADER,
    CROSS_ORIGIN_OPENER_POLICY_HEADER,
    CROSS_ORIGIN_RESOURCE_POLICY_HEADER,
    PERMISSIONS_POLICY_HEADER,
    REFERRER_POLICY_HEADER,
    STRICT_TRANSPORT_SECURITY_HEADER,
)
from app.config import Environment
from app.domain.enums import UserRole
from tests.support.factories import Factory
from tests.support.request_probe import PROBE_PREFIX
from tests.support.tokens import authorization_header, mint_access_token

HEALTH_PATH: Final[str] = "/api/health"
ME_PATH: Final[str] = "/api/me"
SIGN_IN_PATH: Final[str] = "/api/auth/login"
UNKNOWN_PATH: Final[str] = "/api/no-such-endpoint"
RESERVATION_PATH: Final[str] = f"{PROBE_PREFIX}/reservations/RES-000123"
FAULT_PATH: Final[str] = f"{PROBE_PREFIX}/faults/F-1"
DOCS_PATH: Final[str] = "/docs"
REDOC_PATH: Final[str] = "/redoc"
OPENAPI_PATH: Final[str] = "/openapi.json"

# Written out in full on purpose. Importing the values from the module under
# test would only prove the module agrees with itself.
EXPECTED_ON_EVERY_RESPONSE: Final[dict[str, str]] = {
    CONTENT_TYPE_OPTIONS_HEADER: "nosniff",
    REFERRER_POLICY_HEADER: "strict-origin-when-cross-origin",
    CROSS_ORIGIN_OPENER_POLICY_HEADER: "same-origin",
    CROSS_ORIGIN_RESOURCE_POLICY_HEADER: "same-origin",
    PERMISSIONS_POLICY_HEADER: "geolocation=(), microphone=(), camera=(), payment=()",
    CONTENT_SECURITY_POLICY_HEADER: "default-src 'none'; frame-ancestors 'none'",
}
EXPECTED_STRICT_TRANSPORT_SECURITY: Final[str] = "max-age=15768000; includeSubDomains"
EXPECTED_NO_STORE: Final[str] = "no-store"

RELAXED_ENVIRONMENTS: Final[list[Environment]] = [Environment.DEVELOPMENT, Environment.TEST]
DEPLOYED_ENVIRONMENTS: Final[list[Environment]] = [Environment.STAGING, Environment.PRODUCTION]

ClientFactory = Callable[[Environment], TestClient]


class TestEveryResponseCarriesTheHeaders:
    """Successes, refusals, unknown paths and faults all leave with the same headers."""

    @pytest.mark.parametrize(
        ("method", "path", "expected_status"),
        [
            ("GET", RESERVATION_PATH, status.HTTP_200_OK),
            ("GET", ME_PATH, status.HTTP_401_UNAUTHORIZED),
            ("GET", UNKNOWN_PATH, status.HTTP_404_NOT_FOUND),
            ("DELETE", HEALTH_PATH, status.HTTP_405_METHOD_NOT_ALLOWED),
            ("POST", SIGN_IN_PATH, status.HTTP_422_UNPROCESSABLE_CONTENT),
            ("GET", FAULT_PATH, status.HTTP_500_INTERNAL_SERVER_ERROR),
            ("GET", OPENAPI_PATH, status.HTTP_200_OK),
        ],
    )
    def test_a_response_of_any_status_carries_every_header(
        self, request_probe_client: TestClient, method: str, path: str, expected_status: int
    ) -> None:
        response = request_probe_client.request(method, path)
        assert response.status_code == expected_status
        for header, expected in EXPECTED_ON_EVERY_RESPONSE.items():
            assert response.headers.get(header) == expected, (
                f"{method} {path} answered {response.status_code} with {header} set to "
                f"{response.headers.get(header)!r}. Expected {expected!r}."
            )

    def test_the_named_constant_is_the_policy_the_design_document_states(self) -> None:
        expected = EXPECTED_ON_EVERY_RESPONSE[CONTENT_SECURITY_POLICY_HEADER]
        assert expected == CONTENT_SECURITY_POLICY_VALUE

    @pytest.mark.parametrize("path", [DOCS_PATH, REDOC_PATH])
    def test_a_documentation_page_keeps_every_header_except_the_json_only_policy(
        self, request_probe_client: TestClient, path: str
    ) -> None:
        response = request_probe_client.get(path)
        assert response.status_code == status.HTTP_200_OK
        assert CONTENT_SECURITY_POLICY_HEADER not in response.headers
        assert response.headers[CONTENT_TYPE_OPTIONS_HEADER] == "nosniff"
        assert response.headers[CROSS_ORIGIN_RESOURCE_POLICY_HEADER] == "same-origin"


class TestStrictTransportSecurity:
    """Sent where the service is reached over HTTPS, which is staging and production."""

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_a_deployed_environment_sends_it(
        self, client_for_environment: ClientFactory, environment: Environment
    ) -> None:
        response = client_for_environment(environment).get(RESERVATION_PATH)
        assert response.status_code == status.HTTP_200_OK
        assert response.headers[STRICT_TRANSPORT_SECURITY_HEADER] == (
            EXPECTED_STRICT_TRANSPORT_SECURITY
        )

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_a_deployed_environment_sends_it_on_an_error_as_well(
        self, client_for_environment: ClientFactory, environment: Environment
    ) -> None:
        response = client_for_environment(environment).get(FAULT_PATH)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.headers[STRICT_TRANSPORT_SECURITY_HEADER] == (
            EXPECTED_STRICT_TRANSPORT_SECURITY
        )

    @pytest.mark.parametrize("environment", RELAXED_ENVIRONMENTS)
    def test_development_and_test_do_not_send_it(
        self, client_for_environment: ClientFactory, environment: Environment
    ) -> None:
        response = client_for_environment(environment).get(RESERVATION_PATH)
        assert response.status_code == status.HTTP_200_OK
        assert STRICT_TRANSPORT_SECURITY_HEADER not in response.headers


class TestNoStoreOnACredentialedRequest:
    """A response built for one caller may not be kept by a cache."""

    def test_a_request_with_a_valid_token_is_answered_no_store(
        self, client: TestClient, session: Session, factory: Factory
    ) -> None:
        account = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        response = client.get(ME_PATH, headers=authorization_header(mint_access_token(account.id)))
        assert response.status_code == status.HTTP_200_OK
        assert response.headers[CACHE_CONTROL_HEADER] == EXPECTED_NO_STORE

    def test_a_request_with_a_token_that_is_refused_is_answered_no_store_too(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(ME_PATH, headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.headers[CACHE_CONTROL_HEADER] == EXPECTED_NO_STORE

    def test_a_request_with_a_cookie_is_answered_no_store(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(
            RESERVATION_PATH, headers={"Cookie": "refresh_session=an-opaque-value"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.headers[CACHE_CONTROL_HEADER] == EXPECTED_NO_STORE

    def test_a_fault_on_a_credentialed_request_is_answered_no_store(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(FAULT_PATH, headers={"Authorization": "Bearer x"})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.headers[CACHE_CONTROL_HEADER] == EXPECTED_NO_STORE

    def test_a_request_with_no_credential_is_not_marked_no_store(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(RESERVATION_PATH)
        assert response.status_code == status.HTTP_200_OK
        assert CACHE_CONTROL_HEADER not in response.headers

    def test_the_named_constant_is_no_store(self) -> None:
        assert CACHE_CONTROL_NO_STORE_VALUE == EXPECTED_NO_STORE
