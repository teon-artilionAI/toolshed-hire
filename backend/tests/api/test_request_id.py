"""Every request has an id, and the id is the same everywhere it appears.

One value ties a response to its log lines. It is returned in the
`X-Request-ID` header, quoted as `requestId` in every problem document and
stamped on every log record written while the request was being served. A
caller who reports a failure can quote that one value, and I can find the
traceback it belongs to.

A caller may supply the id, so a proxy in front of the service can carry its
own through. Only a valid UUID is accepted. Anything else is replaced, because
the value is written to a response header and to the log, and neither is a
place for text an attacker chose.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response

from app.api.errors import GENERIC_SERVER_ERROR_DETAIL
from app.api.request_middleware import REQUEST_ID_HEADER
from tests.support.http import problem_code, problem_of
from tests.support.log_capture import LogCapture
from tests.support.request_probe import FAULT_DATABASE_PASSWORD, PROBE_PREFIX

HEALTH_PATH: Final[str] = "/api/health"
ME_PATH: Final[str] = "/api/me"
SIGN_IN_PATH: Final[str] = "/api/auth/login"
UNKNOWN_PATH: Final[str] = "/api/no-such-endpoint"
RESERVATION_PATH: Final[str] = f"{PROBE_PREFIX}/reservations/RES-000123"
FAULT_PATH: Final[str] = f"{PROBE_PREFIX}/faults/F-1"
BROKEN_STREAM_PATH: Final[str] = f"{PROBE_PREFIX}/streams/S-1"

SUPPLIED_REQUEST_ID: Final[str] = "0b9d6f4e-52a1-4c3e-9f10-7a2b3c4d5e6f"
UUID_VERSION_FOUR: Final[int] = 4
UNHANDLED_EXCEPTION_EVENT: Final[str] = "api.unhandled_exception"
SERVER_ERROR_PROBLEM: Final[str] = "internal-server-error"
REQUEST_ID_LOG_KEY: Final[str] = "request_id"

# Values that are not a UUID. The last one is what an attempt to write into the
# log or the response through this header looks like.
REJECTED_REQUEST_IDS: Final[list[str]] = [
    "not-a-uuid",
    "12345",
    f"{SUPPLIED_REQUEST_ID}-and-more",
    "<script>alert(1)</script>",
]


def request_id_of(response: Response) -> str:
    """Return the request id header, failing clearly when it is absent."""
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id is not None, (
        f"The response carried no {REQUEST_ID_HEADER} header, so nothing ties it to its log lines."
    )
    return request_id


class TestTheRequestIdHeader:
    """The id a response carries, and where it came from."""

    def test_a_request_with_no_id_is_given_a_new_uuid4(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(RESERVATION_PATH)
        assert response.status_code == status.HTTP_200_OK
        assert UUID(request_id_of(response)).version == UUID_VERSION_FOUR

    def test_two_requests_are_given_different_ids(self, request_probe_client: TestClient) -> None:
        first = request_probe_client.get(RESERVATION_PATH)
        second = request_probe_client.get(RESERVATION_PATH)
        assert request_id_of(first) != request_id_of(second)

    def test_a_valid_uuid_supplied_by_the_caller_is_kept(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(
            RESERVATION_PATH, headers={REQUEST_ID_HEADER: SUPPLIED_REQUEST_ID}
        )
        assert request_id_of(response) == SUPPLIED_REQUEST_ID

    def test_a_supplied_uuid_is_returned_in_its_canonical_form(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(
            RESERVATION_PATH, headers={REQUEST_ID_HEADER: SUPPLIED_REQUEST_ID.upper()}
        )
        assert request_id_of(response) == SUPPLIED_REQUEST_ID

    @pytest.mark.parametrize("rejected", REJECTED_REQUEST_IDS)
    def test_a_supplied_value_that_is_not_a_uuid_is_replaced(
        self, request_probe_client: TestClient, rejected: str
    ) -> None:
        response = request_probe_client.get(RESERVATION_PATH, headers={REQUEST_ID_HEADER: rejected})
        returned = request_id_of(response)
        assert returned != rejected
        assert UUID(returned).version == UUID_VERSION_FOUR

    def test_a_rejected_value_never_reaches_the_log(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        rejected = REJECTED_REQUEST_IDS[-1]
        request_probe_client.get(RESERVATION_PATH, headers={REQUEST_ID_HEADER: rejected})
        assert rejected not in application_log.text

    def test_an_error_response_carries_the_id_as_well(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(ME_PATH)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert UUID(request_id_of(response)).version == UUID_VERSION_FOUR


class TestTheProblemDocumentQuotesTheRequestId:
    """`requestId` in the body is the value in the header, for every kind of error."""

    @pytest.mark.parametrize(
        ("method", "path", "body", "expected_status"),
        [
            ("GET", ME_PATH, None, status.HTTP_401_UNAUTHORIZED),
            ("GET", UNKNOWN_PATH, None, status.HTTP_404_NOT_FOUND),
            ("DELETE", HEALTH_PATH, None, status.HTTP_405_METHOD_NOT_ALLOWED),
            ("POST", SIGN_IN_PATH, {"email": "no"}, status.HTTP_422_UNPROCESSABLE_CONTENT),
            ("GET", FAULT_PATH, None, status.HTTP_500_INTERNAL_SERVER_ERROR),
        ],
    )
    def test_the_document_and_the_header_agree(
        self,
        request_probe_client: TestClient,
        method: str,
        path: str,
        body: dict[str, str] | None,
        expected_status: int,
    ) -> None:
        response = request_probe_client.request(method, path, json=body)
        assert response.status_code == expected_status
        assert problem_of(response)["requestId"] == request_id_of(response)

    def test_a_supplied_id_is_the_one_the_document_quotes(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(
            ME_PATH, headers={REQUEST_ID_HEADER: SUPPLIED_REQUEST_ID}
        )
        assert problem_of(response)["requestId"] == SUPPLIED_REQUEST_ID


class TestEveryLogRecordOfARequestCarriesItsId:
    """The id is stamped by the log handler, so no call site has to remember it."""

    def test_every_record_written_while_serving_a_request_names_that_request(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(ME_PATH, headers={REQUEST_ID_HEADER: SUPPLIED_REQUEST_ID})
        entries = application_log.application_entries()
        # The refusal and the access log line, at the least.
        assert len(entries) >= 2
        assert {entry.get(REQUEST_ID_LOG_KEY) for entry in entries} == {SUPPLIED_REQUEST_ID}

    def test_a_record_written_after_the_request_carries_no_id(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(RESERVATION_PATH)
        application_log.clear()
        logging.getLogger("app.outside_any_request").info("test.written_after_the_request")
        assert REQUEST_ID_LOG_KEY not in application_log.only("test.written_after_the_request")


class TestAnUnhandledFaultIsLoggedWithACorrelationId:
    """The generic 500 says the fault was logged with a correlation id. It was."""

    def test_the_caller_gets_a_generic_document_and_nothing_about_the_fault(
        self, request_probe_client: TestClient
    ) -> None:
        response = request_probe_client.get(FAULT_PATH)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert problem_code(response) == SERVER_ERROR_PROBLEM
        assert problem_of(response)["detail"] == GENERIC_SERVER_ERROR_DETAIL
        assert "Traceback" not in response.text
        assert "RuntimeError" not in response.text
        assert FAULT_DATABASE_PASSWORD not in response.text

    def test_the_traceback_is_logged_once_under_the_id_the_caller_was_given(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        response = request_probe_client.get(FAULT_PATH)
        fault = application_log.only(UNHANDLED_EXCEPTION_EVENT)
        assert fault[REQUEST_ID_LOG_KEY] == problem_of(response)["requestId"]
        assert fault["severity"] == "ERROR"
        assert fault["exception_type"] == "RuntimeError"
        assert "RuntimeError" in str(fault["exception"])

    def test_a_secret_in_the_fault_message_does_not_reach_the_log(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        request_probe_client.get(FAULT_PATH)
        assert FAULT_DATABASE_PASSWORD not in application_log.text

    def test_a_fault_after_the_response_started_is_still_logged_under_its_id(
        self, request_probe_client: TestClient, application_log: LogCapture
    ) -> None:
        response = request_probe_client.get(BROKEN_STREAM_PATH)
        # The head had already gone out, so the status cannot be taken back.
        assert response.status_code == status.HTTP_200_OK
        fault = application_log.only(UNHANDLED_EXCEPTION_EVENT)
        assert fault[REQUEST_ID_LOG_KEY] == request_id_of(response)
