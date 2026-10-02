"""The clock, and the rule for which day it is.

Toolshed Hire trades in Cape Town, so the business day is the day in
`Africa/Johannesburg`, two hours ahead of UTC all year. The case that matters
is the two hours either side of midnight, where the server's UTC date and the
date at the counter disagree. A booking made at half past midnight belongs to
the new day.

The last test reads the source of the two inner layers. After this change
nothing in the domain or the application layer asks the operating system for
the time, and a rule that only holds while everybody remembers it is not a
rule. This is what remembers it.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final

import pytest

from app.application.clock import BUSINESS_TIME_ZONE, Clock, business_day
from app.infrastructure.clock import SystemClock
from tests.support.clock import DEFAULT_INSTANT, FixedClock

# Half past ten at night in UTC on the ninth is half past midnight on the tenth
# in Cape Town.
LATE_EVENING_UTC: Final[datetime] = datetime(2026, 3, 9, 22, 30, tzinfo=UTC)
JUST_BEFORE_MIDNIGHT_IN_CAPE_TOWN: Final[datetime] = datetime(2026, 3, 9, 21, 59, tzinfo=UTC)
NINTH: Final[date] = date(2026, 3, 9)
TENTH: Final[date] = date(2026, 3, 10)
TOLERANCE: Final[timedelta] = timedelta(seconds=5)

APP_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "app"
INNER_LAYERS: Final[tuple[str, ...]] = ("domain", "application")
# The calls that read the wall clock. Written as a pattern over the source so
# an aliased import is caught as well as the plain spelling.
WALL_CLOCK_CALL: Final[re.Pattern[str]] = re.compile(
    r"\b(datetime\.now|datetime\.utcnow|datetime\.today|date\.today|time\.time)\s*\("
)


class TestTheBusinessDay:
    """An instant becomes a day in Africa/Johannesburg, whatever zone it arrived in."""

    def test_the_business_zone_is_johannesburg(self) -> None:
        assert BUSINESS_TIME_ZONE == "Africa/Johannesburg"

    def test_late_evening_in_utc_is_already_the_next_day_in_cape_town(self) -> None:
        assert business_day(LATE_EVENING_UTC) == TENTH

    def test_one_minute_before_midnight_in_cape_town_is_still_the_same_day(self) -> None:
        assert business_day(JUST_BEFORE_MIDNIGHT_IN_CAPE_TOWN) == NINTH

    def test_the_zone_the_instant_arrived_in_does_not_change_the_answer(self) -> None:
        new_york = timezone(timedelta(hours=-5))
        assert business_day(LATE_EVENING_UTC.astimezone(new_york)) == TENTH

    def test_an_instant_with_no_time_zone_is_refused(self) -> None:
        with pytest.raises(ValueError, match="has no time zone"):
            business_day(datetime(2026, 3, 9, 22, 30))


class TestTheSystemClock:
    """The one place the application reads the time from."""

    def test_now_is_the_current_instant_in_utc(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is UTC
        assert abs(datetime.now(UTC) - now) < TOLERANCE

    def test_today_is_the_business_day_of_the_current_instant(self) -> None:
        clock = SystemClock(instant_source=lambda: LATE_EVENING_UTC)
        assert clock.now() == LATE_EVENING_UTC
        assert clock.today() == TENTH

    def test_an_instant_source_in_another_zone_is_still_reported_in_utc(self) -> None:
        cape_town = timezone(timedelta(hours=2))
        clock = SystemClock(instant_source=lambda: LATE_EVENING_UTC.astimezone(cape_town))
        assert clock.now().tzinfo is UTC
        assert clock.now() == LATE_EVENING_UTC

    def test_it_satisfies_the_clock_port(self) -> None:
        clock: Clock = SystemClock()
        assert isinstance(clock.today(), date)


class TestTheFixedClock:
    """The clock the tests hand to a use case."""

    def test_it_returns_the_instant_it_was_given_every_time(self) -> None:
        clock = FixedClock(LATE_EVENING_UTC)
        assert clock.now() == LATE_EVENING_UTC
        assert clock.now() == LATE_EVENING_UTC

    def test_its_day_is_the_business_day_and_not_the_utc_day(self) -> None:
        assert FixedClock(LATE_EVENING_UTC).today() == TENTH

    def test_it_only_moves_when_a_test_moves_it(self) -> None:
        clock = FixedClock(JUST_BEFORE_MIDNIGHT_IN_CAPE_TOWN)
        assert clock.today() == NINTH
        clock.advance(timedelta(minutes=1))
        assert clock.today() == TENTH

    def test_the_default_instant_is_a_week_before_the_worked_example_hire(self) -> None:
        assert FixedClock().today() == DEFAULT_INSTANT.date() == date(2026, 3, 2)


class TestNothingInTheInnerLayersReadsTheWallClock:
    """The domain and the application layer are given the time. They never take it."""

    @pytest.mark.parametrize("layer", INNER_LAYERS)
    def test_no_source_file_calls_the_wall_clock(self, layer: str) -> None:
        offenders = [
            f"{path.relative_to(APP_ROOT)}:{number}"
            for path in sorted((APP_ROOT / layer).rglob("*.py"))
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if WALL_CLOCK_CALL.search(line)
        ]
        assert offenders == [], (
            f"The {layer} layer reads the wall clock directly at {offenders}. Take a Clock "
            "through the constructor and ask it instead, so a test can hold the time still."
        )

    @pytest.mark.parametrize("layer", INNER_LAYERS)
    def test_the_layer_has_source_files_to_check(self, layer: str) -> None:
        assert list((APP_ROOT / layer).rglob("*.py")), (
            f"Found no source under {APP_ROOT / layer}, so the check above checked nothing."
        )
