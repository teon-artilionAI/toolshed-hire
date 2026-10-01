"""The log scrub test (C-42).

A secret that reaches the log has been published, so this does not test that
call sites are careful. It logs the four things that must never be written, a
password, a bearer token, a refresh cookie and a database URL, through the
application's real log handler, and asserts that none of them is in the output.

The first class reads the output of the real handler. The rest pin the two
rules of the filter one at a time, including the cases it must leave alone,
because a filter that redacts an ordinary address is one somebody switches off.
"""

from __future__ import annotations

import io
import logging
from typing import Final

import pytest

from app.log_redaction import (
    MAXIMUM_NESTING_DEPTH,
    NESTING_LIMIT_PLACEHOLDER,
    REDACTED_PLACEHOLDER,
    SENSITIVE_KEY_FRAGMENTS,
    is_sensitive_key,
    scrub_text,
    scrub_value,
)
from app.logging_config import build_handler
from tests.support.log_capture import LogCapture

logger = logging.getLogger("app.tests.log_scrub")

PASSWORD: Final[str] = "correct-horse-battery-staple-9431"
BEARER_TOKEN: Final[str] = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzY3J1YiJ9.c2lnbmF0dXJlLXZhbHVl"
REFRESH_COOKIE: Final[str] = "rc_7Qd1mXv0pZk2LwYh8uT4sNe6"
DATABASE_PASSWORD: Final[str] = "npg_Zx81kQwLm3TrVb"
DATABASE_URL: Final[str] = (
    f"postgresql+psycopg://toolshed_app:{DATABASE_PASSWORD}@ep-example-pooler.example.test/toolshed"
)
API_KEY: Final[str] = "sk_live_4f9a2c7d1e8b"
ALL_SECRETS: Final[list[str]] = [
    PASSWORD,
    BEARER_TOKEN,
    REFRESH_COOKIE,
    DATABASE_PASSWORD,
    API_KEY,
]
SCRUBBED_DATABASE_URL: Final[str] = (
    f"postgresql+psycopg://toolshed_app:{REDACTED_PLACEHOLDER}@ep-example-pooler.example.test/toolshed"
)


def assert_no_secret_in(output: str) -> None:
    """Fail, naming the secret, if any of them was written."""
    for secret in ALL_SECRETS:
        assert secret not in output, f"The log output contains the secret {secret!r}."


class TestNoSecretReachesTheLog:
    """The four secrets, logged every way a call site could log them."""

    def test_secrets_passed_as_extra_fields_are_not_written(
        self, application_log: LogCapture
    ) -> None:
        logger.info(
            "test.scrub_extra_fields",
            extra={
                "password": PASSWORD,
                "authorization": f"Bearer {BEARER_TOKEN}",
                "refresh_cookie": REFRESH_COOKIE,
                "database_url": DATABASE_URL,
            },
        )
        entry = application_log.only("test.scrub_extra_fields")
        assert_no_secret_in(application_log.text)
        assert entry["password"] == REDACTED_PLACEHOLDER
        assert entry["authorization"] == REDACTED_PLACEHOLDER
        assert entry["refresh_cookie"] == REDACTED_PLACEHOLDER
        assert entry["database_url"] == REDACTED_PLACEHOLDER

    def test_key_names_are_matched_whatever_their_case_and_whatever_surrounds_them(
        self, application_log: LogCapture
    ) -> None:
        logger.warning(
            "test.scrub_key_variants",
            extra={
                "newPassword": PASSWORD,
                "ACCESS_TOKEN": BEARER_TOKEN,
                "Set-Cookie": f"refresh={REFRESH_COOKIE}; HttpOnly",
                "client_secret": PASSWORD,
                "stripe_api_key": API_KEY,
                "DATABASE_URL": DATABASE_URL,
            },
        )
        assert_no_secret_in(application_log.text)
        assert application_log.text.count(REDACTED_PLACEHOLDER) == 6

    def test_secrets_nested_inside_a_value_are_not_written(
        self, application_log: LogCapture
    ) -> None:
        logger.info(
            "test.scrub_nested",
            extra={
                "detail": {
                    "headers": {
                        "Authorization": f"Bearer {BEARER_TOKEN}",
                        "Cookie": REFRESH_COOKIE,
                    },
                    "attempts": [{"password": PASSWORD}, {"dsn": DATABASE_URL}],
                }
            },
        )
        assert_no_secret_in(application_log.text)

    def test_a_database_url_in_the_message_keeps_its_host_and_loses_its_password(
        self, application_log: LogCapture
    ) -> None:
        logger.error("could not connect to %s after %d attempts", DATABASE_URL, 3)
        assert_no_secret_in(application_log.text)
        message = str(application_log.entries()[0]["message"])
        assert message == f"could not connect to {SCRUBBED_DATABASE_URL} after 3 attempts"

    def test_a_database_url_under_a_harmless_key_loses_its_password(
        self, application_log: LogCapture
    ) -> None:
        logger.error("test.scrub_value", extra={"error": f"connection to {DATABASE_URL} refused"})
        entry = application_log.only("test.scrub_value")
        assert entry["error"] == f"connection to {SCRUBBED_DATABASE_URL} refused"

    def test_a_database_url_in_a_traceback_loses_its_password(
        self, application_log: LogCapture
    ) -> None:
        try:
            raise ConnectionError(f"could not connect to {DATABASE_URL}")
        except ConnectionError:
            logger.exception("test.scrub_traceback")
        entry = application_log.only("test.scrub_traceback")
        assert_no_secret_in(application_log.text)
        assert SCRUBBED_DATABASE_URL in str(entry["exception"])

    def test_an_object_that_is_not_json_is_scrubbed_through_its_text(
        self, application_log: LogCapture
    ) -> None:
        logger.error("test.scrub_object", extra={"cause": ConnectionError(DATABASE_URL)})
        assert_no_secret_in(application_log.text)
        assert application_log.only("test.scrub_object")["cause"] == SCRUBBED_DATABASE_URL

    def test_an_ordinary_record_is_written_unchanged(self, application_log: LogCapture) -> None:
        logger.info(
            "test.scrub_ordinary",
            extra={
                "asset_tag": "TSH-DRL-0007",
                "quantity": 2,
                "available": True,
                "branches": ["CBD"],
            },
        )
        entry = application_log.only("test.scrub_ordinary")
        assert entry["asset_tag"] == "TSH-DRL-0007"
        assert entry["quantity"] == 2
        assert entry["available"] is True
        assert entry["branches"] == ["CBD"]
        assert REDACTED_PLACEHOLDER not in application_log.text


class TestSensitiveKeyNames:
    """A key is sensitive when its name contains one of the listed fragments."""

    @pytest.mark.parametrize("fragment", SENSITIVE_KEY_FRAGMENTS)
    def test_every_listed_fragment_marks_a_key(self, fragment: str) -> None:
        assert is_sensitive_key(fragment)
        assert is_sensitive_key(f"old_{fragment.upper()}_value")

    @pytest.mark.parametrize("name", ["email", "user_id", "status", "route", "duration_ms"])
    def test_an_ordinary_key_is_not_marked(self, name: str) -> None:
        assert not is_sensitive_key(name)


class TestConnectionStrings:
    """Only the password of a connection string is replaced."""

    @pytest.mark.parametrize(
        "scheme", ["postgresql", "postgresql+psycopg", "postgres", "redis", "amqp", "https"]
    )
    def test_the_password_is_replaced_for_any_scheme(self, scheme: str) -> None:
        scrubbed = scrub_text(f"{scheme}://user:{DATABASE_PASSWORD}@host.example:5432/name")
        assert scrubbed == f"{scheme}://user:{REDACTED_PLACEHOLDER}@host.example:5432/name"

    def test_every_connection_string_in_a_text_is_scrubbed(self) -> None:
        text = f"primary {DATABASE_URL} replica {DATABASE_URL}"
        assert DATABASE_PASSWORD not in scrub_text(text)
        assert scrub_text(text).count(REDACTED_PLACEHOLDER) == 2

    @pytest.mark.parametrize(
        "harmless",
        [
            "http://localhost:8000/api/health",
            "https://toolshedhire.co.za/problems/not-found",
            "postgresql+psycopg://db.internal:5432/toolshed",
            "mailed thabo@example.co.za at 10:45",
            "http://localhost:5173/account?next=a@b.example",
        ],
    )
    def test_a_text_with_no_password_in_it_is_left_alone(self, harmless: str) -> None:
        assert scrub_text(harmless) == harmless


class TestValuesAreWalked:
    """Secrets are found at any depth, and the walk always ends."""

    def test_plain_json_values_pass_through_unchanged(self) -> None:
        assert scrub_value(None) is None
        assert scrub_value(True) is True
        assert scrub_value(7) == 7
        assert scrub_value(1.5) == 1.5

    def test_a_structure_that_contains_itself_does_not_recurse_without_end(self) -> None:
        endless: dict[str, object] = {"password": PASSWORD}
        endless["again"] = endless
        scrubbed = str(scrub_value(endless))
        assert PASSWORD not in scrubbed
        assert scrubbed.count("again") == MAXIMUM_NESTING_DEPTH
        assert NESTING_LIMIT_PLACEHOLDER in scrubbed


class TestARecordThatCannotBeFormatted:
    """A format string that does not fit its arguments is a fault logging reports itself.

    It reports it by printing the message and the arguments, so the filter has
    to leave both clean even though it cannot merge them. This is checked on
    the record, through the filters of the real handler, because what logging
    does next with such a record depends on which handlers are attached.
    """

    def test_the_message_and_positional_arguments_are_scrubbed_where_they_stand(self) -> None:
        record = logging.LogRecord(
            name="app.tests.log_scrub",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=f"primary {DATABASE_URL} then %s and %s",
            args=(DATABASE_URL,),
            exc_info=None,
        )
        assert build_handler(io.StringIO()).filter(record)
        assert DATABASE_PASSWORD not in str(record.msg)
        assert record.args == (SCRUBBED_DATABASE_URL,)

    def test_named_arguments_are_scrubbed_where_they_stand(self) -> None:
        record = logging.LogRecord(
            name="app.tests.log_scrub",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="connecting to %(dsn)s as %(missing)s",
            args=({"dsn": DATABASE_URL},),
            exc_info=None,
        )
        assert build_handler(io.StringIO()).filter(record)
        assert record.args == {"dsn": SCRUBBED_DATABASE_URL}
