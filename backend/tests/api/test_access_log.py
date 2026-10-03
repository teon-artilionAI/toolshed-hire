"""One access log line per request, and what it says.

The line is written when the response is finished. It names the method, the
route as a template, the status, how long the request took, the role of the
caller and whether the request succeeded, and it carries the request id.

Three things are pinned with care. The route is the template and never the
path that was requested, because a path holds identifiers. The role comes from
the account the authentication dependency loaded, so the middleware asks the
database nothing. And the level follows the outcome, so a query for errors
finds the requests that failed.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.request_middleware import (
    ACCESS_LOG_EVENT,
    OUTCOME_CLIENT_ERROR,
    OUTCOME_SERVER_ERROR,
    OUTCOME_SUCCESS,
    REQUEST_ID_HEADER,
    UNMATCHED_ROUTE,
)
from app.domain.enums import UserRole
from app.request_context import ANONYMOUS_ACTOR_ROLE
from tests.support.factories import Factory
from tests.support.log_capture import LogCapture
from tests.support.request_probe import (
    BROKEN_STREAM_ROUTE_TEMPLATE,
    FAULT_ROUTE_TEMPLATE,
    PROBE_PREFIX,
    RESERVATION_ROUTE_TEMPLATE,
)
from tests.support.tokens import (
    authorization_header,
    mint_access_token,
    mint_token_signed_with_a_foreign_key,
)

ME_PATH: Final[str] = "/api/me"
ME_ROUTE_TEMPLATE: Final[str] = "/api/me"
SIGN_IN_PATH: Final[str] = "/api/auth/login"
SIGN_IN_ROUTE_TEMPLATE: Final[str] = "/api/auth/login"
HEALTH_PATH: Final[str] = "/api/health"
HEALTH_ROUTE_TEMPLATE: Final[str] = "/api/health"
RESERVATION_IDENTIFIER: Final[str] = "RES-000123"
RESERVATION_PATH: Final[str] = f"{PROBE_PREFIX}/reservations/{RESERVATION_IDENTIFIER}"
FAULT_PATH: Final[str] = f"{PROBE_PREFIX}/faults/F-1"
BROKEN_STREAM_PATH: Final[str] = f"{PROBE_PREFIX}/streams/S-1"
UNKNOWN_IDENTIFIER: Final[str] = "CUST-778899"
# A path no router serves. It used to sit under /api/customers, which the
# counter's customer routes now serve.
UNKNOWN_PATH: Final[str] = f"/api/no-such-collection/{UNKNOWN_IDENTIFIER}"

ACCESS_LOG_FIELDS: Final[set[str]] = {
    "method",
    "route",
    "status",
    "duration_ms",
    "actor_role",
    "outcome",
    "request_id",
}


class TestTheAccessLogLine:
    """What one finished request leaves in the log."""

    def test_a_request_writes_exactly_one_line_with_every_field(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        response = request_probe_client.get(RESERVATION_PATH)
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line.keys() >= ACCESS_LOG_FIELDS
        assert line["method"] == "GET"
        assert line["status"] == status.HTTP_200_OK
        assert line["outcome"] == OUTCOME_SUCCESS
        assert line["actor_role"] == ANONYMOUS_ACTOR_ROLE
        assert line["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_the_duration_is_a_number_of_milliseconds(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(RESERVATION_PATH)
        duration = application_log.only(ACCESS_LOG_EVENT)["duration_ms"]
        assert isinstance(duration, int | float)
        assert duration >= 0

    def test_the_route_is_the_template_and_the_identifier_is_not_logged(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(RESERVATION_PATH)
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["route"] == RESERVATION_ROUTE_TEMPLATE
        assert RESERVATION_IDENTIFIER not in str(line)

    def test_the_template_includes_the_prefix_of_every_router_it_was_included_through(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.post(SIGN_IN_PATH, json={"email": "no"})
        assert application_log.only(ACCESS_LOG_EVENT)["route"] == SIGN_IN_ROUTE_TEMPLATE

    def test_a_path_that_matches_no_route_is_logged_without_the_path(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        response = request_probe_client.get(UNKNOWN_PATH)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["route"] == UNMATCHED_ROUTE
        assert UNKNOWN_IDENTIFIER not in str(line)

    def test_a_method_the_route_does_not_allow_is_still_logged_against_its_template(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        response = request_probe_client.delete(HEALTH_PATH)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["method"] == "DELETE"
        assert line["route"] == HEALTH_ROUTE_TEMPLATE


class TestTheOutcomeAndTheLevel:
    """Success is info, a client error is a warning and a server error is an error."""

    def test_a_successful_request_is_logged_at_info(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(RESERVATION_PATH)
        assert application_log.only(ACCESS_LOG_EVENT)["severity"] == "INFO"

    @pytest.mark.parametrize(
        ("method", "path", "expected_status"),
        [
            ("GET", ME_PATH, status.HTTP_401_UNAUTHORIZED),
            ("GET", UNKNOWN_PATH, status.HTTP_404_NOT_FOUND),
            ("POST", SIGN_IN_PATH, status.HTTP_422_UNPROCESSABLE_CONTENT),
        ],
    )
    def test_a_request_the_caller_got_wrong_is_a_client_error_at_warning(
        self,
        request_probe_client: TestClient,
        application_log: LogCapture,
        method: str,
        path: str,
        expected_status: int,
    ) -> None:
        request_probe_client.request(method, path)
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["status"] == expected_status
        assert line["outcome"] == OUTCOME_CLIENT_ERROR
        assert line["severity"] == "WARNING"

    def test_an_unhandled_fault_is_a_server_error_at_error(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(FAULT_PATH)
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["status"] == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert line["outcome"] == OUTCOME_SERVER_ERROR
        assert line["severity"] == "ERROR"
        assert line["route"] == FAULT_ROUTE_TEMPLATE

    def test_a_degraded_health_check_is_a_server_error(
        self, client: TestClient, application_log: LogCapture
    ) -> None:
        # The in memory database has no btree_gist, so the check reports 503.
        response = client.get(HEALTH_PATH)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["route"] == HEALTH_ROUTE_TEMPLATE
        assert line["outcome"] == OUTCOME_SERVER_ERROR
        assert line["severity"] == "ERROR"

    def test_a_fault_after_the_response_started_is_a_server_error_whatever_was_sent(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(BROKEN_STREAM_PATH)
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["status"] == status.HTTP_200_OK
        assert line["outcome"] == OUTCOME_SERVER_ERROR
        assert line["severity"] == "ERROR"
        assert line["route"] == BROKEN_STREAM_ROUTE_TEMPLATE


class TestTheActorRole:
    """Who made the request, as the authentication dependency recorded it."""

    @pytest.mark.parametrize("role", list(UserRole))
    def test_an_authenticated_request_is_logged_with_the_stored_role(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        application_log: LogCapture,
        role: UserRole,
    ) -> None:
        branch = factory.branch() if role is UserRole.COUNTER_STAFF else None
        account = factory.user(role=role, branch=branch)
        session.commit()
        application_log.clear()
        response = client.get(ME_PATH, headers=authorization_header(mint_access_token(account.id)))
        assert response.status_code == status.HTTP_200_OK
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["actor_role"] == role.value
        assert line["route"] == ME_ROUTE_TEMPLATE

    def test_a_request_with_no_credential_is_anonymous(
        self, client: TestClient, application_log: LogCapture
    ) -> None:
        client.get(ME_PATH)
        assert application_log.only(ACCESS_LOG_EVENT)["actor_role"] == ANONYMOUS_ACTOR_ROLE

    def test_a_request_with_a_forged_token_is_anonymous(
        self, client: TestClient, session: Session, factory: Factory, application_log: LogCapture
    ) -> None:
        account = factory.user(role=UserRole.ADMIN)
        session.commit()
        application_log.clear()
        forged = mint_token_signed_with_a_foreign_key(account.id)
        response = client.get(ME_PATH, headers=authorization_header(forged))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert application_log.only(ACCESS_LOG_EVENT)["actor_role"] == ANONYMOUS_ACTOR_ROLE

    def test_a_deactivated_account_is_refused_and_still_logged_with_its_role(
        self, client: TestClient, session: Session, factory: Factory, application_log: LogCapture
    ) -> None:
        account = factory.user(role=UserRole.CUSTOMER)
        account.is_active = False
        session.add(account)
        session.commit()
        application_log.clear()
        response = client.get(ME_PATH, headers=authorization_header(mint_access_token(account.id)))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        line = application_log.only(ACCESS_LOG_EVENT)
        assert line["actor_role"] == UserRole.CUSTOMER.value
        assert line["outcome"] == OUTCOME_CLIENT_ERROR

    def test_the_role_of_one_request_does_not_leak_into_the_next(
        self, client: TestClient, session: Session, factory: Factory, application_log: LogCapture
    ) -> None:
        account = factory.user(role=UserRole.ADMIN)
        session.commit()
        client.get(ME_PATH, headers=authorization_header(mint_access_token(account.id)))
        application_log.clear()
        client.get(ME_PATH)
        assert application_log.only(ACCESS_LOG_EVENT)["actor_role"] == ANONYMOUS_ACTOR_ROLE

    def test_the_access_log_never_contains_the_bearer_token(
        self, client: TestClient, session: Session, factory: Factory, application_log: LogCapture
    ) -> None:
        account = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        token = mint_access_token(account.id)
        client.get(ME_PATH, headers=authorization_header(token))
        assert token not in application_log.text
