"""The settings that start the clock of a test process at a chosen date and time.

The browser tests book a hire for today and check it out. A hire can only
start today while the collection branch is open (BR-04), so a run after
closing time would fail for a reason that has nothing to do with the change
under test. `TEST_BUSINESS_TIME`, for example `10:00`, makes the clock the API
uses report today's real date at that time of day in Cape Town when the
process starts, and then run on in real time from there.

`TEST_BUSINESS_DATE`, for example `2026-12-16`, moves the date as well, for a
test-only calendar qualification. It needs `TEST_BUSINESS_TIME`, and it is
honoured only when `ENVIRONMENT=test`. `config.py` refuses to start any other
environment that sets either, so a deployed service can never run on a clock
that lies about the date or time. The clock itself is built in
`app.infrastructure.clock`.

It lives in a class of its own so that `config.py` stays a list of the other
settings. `Settings` inherits from this class, so the setting is read from the
same environment in the same pass.
"""

from __future__ import annotations

from datetime import date, time
from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

TEST_BUSINESS_TIME_VARIABLE: Final[str] = "TEST_BUSINESS_TIME"
TEST_BUSINESS_DATE_VARIABLE: Final[str] = "TEST_BUSINESS_DATE"


class ClockSettings(BaseSettings):
    """The time of day a test process starts its clock at, or None for the real clock."""

    test_business_time: time | None = Field(
        default=None,
        validation_alias=TEST_BUSINESS_TIME_VARIABLE,
        description="Test only. The time of day in Cape Town the clock starts at, such as 10:00",
    )
    test_business_date: date | None = Field(
        default=None,
        validation_alias=TEST_BUSINESS_DATE_VARIABLE,
        description="Test only. The date in Cape Town the clock starts at, such as 2026-12-16",
    )

    @field_validator("test_business_time", "test_business_date", mode="before")
    @classmethod
    def read_blank_as_unset(cls, value: object) -> object:
        """Read a blank value as no test clock at all."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


def check_test_clock(
    configured_time: time | None,
    configured_date: date | None,
    *,
    environment: str,
    is_test: bool,
) -> None:
    """Refuse a test clock in any environment but test.

    Raises:
        ValueError: If either test clock setting is set outside test, or a
            date is set without a time. The message names the variable and
            the environment.

    """
    if configured_date is not None and configured_time is None:
        raise ValueError(
            f"{TEST_BUSINESS_DATE_VARIABLE} needs {TEST_BUSINESS_TIME_VARIABLE}. Set both, "
            "or unset the date."
        )
    if (configured_time is None and configured_date is None) or is_test:
        return
    names = ", ".join(
        name
        for name, value in (
            (TEST_BUSINESS_TIME_VARIABLE, configured_time),
            (TEST_BUSINESS_DATE_VARIABLE, configured_date),
        )
        if value is not None
    )
    raise ValueError(
        f"{names} set in environment {environment!r}. The test clock is honoured only when "
        "ENVIRONMENT=test. Unset it."
    )
