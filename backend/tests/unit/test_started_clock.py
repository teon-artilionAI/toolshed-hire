"""The clock a test process starts at a chosen time of day, and where it is refused.

`TEST_BUSINESS_TIME` makes the clock the API uses report today's real date at
that time of day in Cape Town when the process starts, and then run on in real
time. The browser tests book for today and check out, so they pass whatever
time CI runs. It is honoured in the test environment only, and any other
environment refuses to start with it set.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Final

import pytest
from pydantic import ValidationError

from app.config import ConfigurationError, Environment, load_settings
from app.infrastructure.clock import StartedAtBusinessTimeClock, SystemClock, clock_for
from tests.support.request_probe import settings_for

TEN_IN_THE_MORNING: Final[time] = time(10, 0)
# 20:30 in Cape Town on Monday the second of March 2026, after every branch has closed.
EVENING: Final[datetime] = datetime(2026, 3, 2, 18, 30, tzinfo=UTC)
# 01:30 in Cape Town on Tuesday the third, while it is still the second in UTC.
JUST_AFTER_MIDNIGHT: Final[datetime] = datetime(2026, 3, 2, 23, 30, tzinfo=UTC)


class MovingSource:
    """The real instant, as a test moves it."""

    def __init__(self, instant: datetime) -> None:
        """Start at an instant."""
        self.instant = instant

    def __call__(self) -> datetime:
        """Return the instant as it stands."""
        return self.instant


class TestTheClock:
    """Today's real date at the time chosen, and then real time."""

    def test_it_starts_at_the_time_chosen_on_todays_real_date(self) -> None:
        clock = StartedAtBusinessTimeClock(TEN_IN_THE_MORNING, MovingSource(EVENING))
        assert clock.now() == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
        assert clock.today() == date(2026, 3, 2)

    def test_it_runs_on_in_real_time(self) -> None:
        source = MovingSource(EVENING)
        clock = StartedAtBusinessTimeClock(TEN_IN_THE_MORNING, source)
        source.instant = EVENING + timedelta(minutes=95)
        assert clock.now() == datetime(2026, 3, 2, 9, 35, tzinfo=UTC)

    def test_the_real_date_is_the_one_in_cape_town(self) -> None:
        clock = StartedAtBusinessTimeClock(TEN_IN_THE_MORNING, MovingSource(JUST_AFTER_MIDNIGHT))
        assert clock.today() == date(2026, 3, 3)
        assert clock.now() == datetime(2026, 3, 3, 8, 0, tzinfo=UTC)

    def test_the_real_clock_is_chosen_when_nothing_is_set(self) -> None:
        assert isinstance(clock_for(None), SystemClock)
        assert isinstance(clock_for(TEN_IN_THE_MORNING), StartedAtBusinessTimeClock)


class TestTheSetting:
    """Honoured in the test environment, refused at start-up in any other."""

    def test_the_test_environment_reads_it(self) -> None:
        loaded = settings_for(Environment.TEST, TEST_BUSINESS_TIME="10:00")
        assert loaded.test_business_time == TEN_IN_THE_MORNING
        assert loaded.redacted()["test_business_time"] == "10:00:00"

    def test_a_blank_value_is_no_test_clock(self) -> None:
        loaded = settings_for(Environment.TEST, TEST_BUSINESS_TIME="  ")
        assert loaded.test_business_time is None
        assert loaded.redacted()["test_business_time"] == "off"

    @pytest.mark.parametrize(
        "environment",
        [Environment.DEVELOPMENT, Environment.STAGING, Environment.PRODUCTION],
    )
    def test_any_other_environment_refuses_it(self, environment: Environment) -> None:
        with pytest.raises(ValidationError, match="honoured only when ENVIRONMENT=test"):
            settings_for(environment, TEST_BUSINESS_TIME="10:00")

    def test_start_up_refuses_it_outside_test(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET", "a-real-signing-key-of-at-least-thirty-two-characters")
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:pw@db.internal:5432/app")
        monkeypatch.setenv("FRONTEND_ORIGIN", "https://toolshed.example")
        monkeypatch.setenv("TEST_BUSINESS_TIME", "10:00")
        with pytest.raises(ConfigurationError, match="TEST_BUSINESS_TIME"):
            load_settings()
