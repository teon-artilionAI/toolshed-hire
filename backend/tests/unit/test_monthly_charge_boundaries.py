"""The monthly charge query uses Cape Town calendar boundaries (B13.3).

The database stores instants in UTC. A month in the bookkeeper's file starts
and ends at midnight in Africa/Johannesburg, which is 22:00 UTC the day before.
SQLite cannot represent the timezone-aware comparison, so this unit test pins
the boundary construction and the PostgreSQL test exercises the query.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.infrastructure.monthly_charges import _start_of


def test_october_starts_at_cape_town_midnight() -> None:
    """1 October 00:00 SAST is 30 September 22:00 UTC."""
    assert _start_of(date(2026, 10, 1)) == datetime(2026, 9, 30, 22, 0, tzinfo=UTC)


def test_january_starts_at_cape_town_midnight() -> None:
    """1 January 00:00 SAST is 31 December 22:00 UTC."""
    assert _start_of(date(2027, 1, 1)) == datetime(2026, 12, 31, 22, 0, tzinfo=UTC)
