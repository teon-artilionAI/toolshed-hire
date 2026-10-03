"""The setting that starts the clock of a test process at a chosen time of day.

The browser tests book a hire for today and check it out. A hire can only
start today while the collection branch is open (BR-04), so a run after
closing time would fail for a reason that has nothing to do with the change
under test. `TEST_BUSINESS_TIME`, for example `10:00`, makes the clock the API
uses report today's real date at that time of day in Cape Town when the
process starts, and then run on in real time from there.

It is honoured only when `ENVIRONMENT=test`. `config.py` refuses to start any
other environment that sets it, so a deployed service can never run on a
clock that lies about the time. The clock itself is built in
`app.infrastructure.clock`.

It lives in a class of its own so that `config.py` stays a list of the other
settings. `Settings` inherits from this class, so the setting is read from the
same environment in the same pass.
"""

from __future__ import annotations

from datetime import time
from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

TEST_BUSINESS_TIME_VARIABLE: Final[str] = "TEST_BUSINESS_TIME"


class ClockSettings(BaseSettings):
    """The time of day a test process starts its clock at, or None for the real clock."""

    test_business_time: time | None = Field(
        default=None,
        validation_alias=TEST_BUSINESS_TIME_VARIABLE,
        description="Test only. The time of day in Cape Town the clock starts at, such as 10:00",
    )

    @field_validator("test_business_time", mode="before")
    @classmethod
    def read_blank_as_unset(cls, value: object) -> object:
        """Read a blank value as no test clock at all."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


def check_test_business_time(configured: time | None, *, environment: str, is_test: bool) -> None:
    """Refuse a test clock in any environment but test.

    Raises:
        ValueError: If `TEST_BUSINESS_TIME` is set and the environment is not
            test. The message names the variable and the environment.

    """
    if configured is None or is_test:
        return
    raise ValueError(
        f"{TEST_BUSINESS_TIME_VARIABLE} is set in environment {environment!r}. It moves the "
        "clock and is honoured only when ENVIRONMENT=test. Unset it."
    )
