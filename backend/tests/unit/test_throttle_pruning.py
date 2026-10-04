"""Pruning the throttle counters, the fourth part of the lazy sweep, with no database (C-17).

A counter whose window ended more than a day ago is deleted, and nothing
younger is. One sweep deletes at most a batch, oldest window first, in a
transaction of its own that commits only when something went, and says how
many went in the log. The statement, its row locks and the index it reads are
proved against PostgreSQL in tests/integration/test_throttle_counter_pruning.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Final

import pytest

from app.application.booking.expire_holds import SweepCommand, SweepResult
from app.application.throttle import LONGEST_THROTTLE_WINDOW
from app.application.throttle_pruning import (
    COUNTER_KEPT_AFTER_WINDOW,
    COUNTER_PRUNE_BATCH_SIZE,
    finished_window_cutoff,
    prune_finished_windows,
)
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory import COMMIT
from tests.support.memory_counters import CounterKey, MemoryRateLimits
from tests.support.memory_world import MemoryWorld, build_memory_world, open_desk

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
CUTOFF: Final[datetime] = DEFAULT_INSTANT - LONGEST_THROTTLE_WINDOW - COUNTER_KEPT_AFTER_WINDOW
JUST_FINISHED_LONG_AGO: Final[CounterKey] = ("an-old-bucket", CUTOFF - ONE_SECOND)
ON_THE_CUTOFF: Final[CounterKey] = ("a-bucket-on-the-edge", CUTOFF)
STILL_RUNNING: Final[CounterKey] = ("a-live-bucket", DEFAULT_INSTANT - ONE_SECOND)
PRUNED_LINE: Final[str] = "throttle.counters_pruned"


def old_counters(count: int) -> dict[CounterKey, int]:
    """Return `count` counters of one bucket, a minute apart, all long finished."""
    return {
        ("an-old-bucket", CUTOFF - timedelta(minutes=minute + 1)): minute + 1
        for minute in range(count)
    }


def sweep(world: MemoryWorld, command: SweepCommand | None = None) -> SweepResult:
    """Run the whole sweep once over the world, on a clock at the default instant."""
    return open_desk(world).sweep.execute(command or SweepCommand())


class TestTheCutoff:
    """A counter goes once its window, however long, ended more than a day ago."""

    def test_the_cutoff_is_the_longest_window_and_a_day_before_now(self) -> None:
        assert finished_window_cutoff(DEFAULT_INSTANT) == CUTOFF
        assert LONGEST_THROTTLE_WINDOW < COUNTER_KEPT_AFTER_WINDOW

    def test_a_counter_before_the_cutoff_goes_and_one_on_it_stays(self) -> None:
        counters = {JUST_FINISHED_LONG_AGO: 3, ON_THE_CUTOFF: 4, STILL_RUNNING: 5}
        assert prune_finished_windows(MemoryRateLimits(counters), DEFAULT_INSTANT, 10) == 1
        assert counters == {ON_THE_CUTOFF: 4, STILL_RUNNING: 5}

    def test_at_most_the_batch_goes_and_the_oldest_first(self) -> None:
        counters = old_counters(5)
        oldest_two = sorted(counters)[:2]
        assert prune_finished_windows(MemoryRateLimits(counters), DEFAULT_INSTANT, 3) == 3
        assert sorted(counters) == sorted(old_counters(5))[3:]
        assert all(key not in counters for key in oldest_two)

    @pytest.mark.parametrize("limit", [0, -1])
    def test_a_batch_of_nothing_is_refused(self, limit: int) -> None:
        with pytest.raises(ValueError, match="A batch is at least one counter"):
            prune_finished_windows(MemoryRateLimits({}), DEFAULT_INSTANT, limit)


class TestTheLogLine:
    """How many went, at INFO when any did and at DEBUG when none did."""

    def test_the_count_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG):
            prune_finished_windows(MemoryRateLimits(old_counters(2)), DEFAULT_INSTANT, 10)
            prune_finished_windows(MemoryRateLimits({}), DEFAULT_INSTANT, 10)
        lines = [record for record in caplog.records if record.getMessage() == PRUNED_LINE]
        assert [(line.levelno, line.__dict__["deleted_count"]) for line in lines] == [
            (logging.INFO, 2),
            (logging.DEBUG, 0),
        ]
        assert lines[0].__dict__["batch_size"] == 10
        assert lines[0].__dict__["window_started_before"] == CUTOFF.isoformat()


class TestTheFourthPartOfTheSweep:
    """The sweep prunes in a transaction of its own, a batch at a time."""

    def test_the_sweep_deletes_what_is_due_and_commits_it(self) -> None:
        world = build_memory_world()
        world.store.committed.counters = {JUST_FINISHED_LONG_AGO: 3, STILL_RUNNING: 5}
        result = sweep(world)
        assert result.pruned_counter_count == 1
        assert world.store.committed.counters == {STILL_RUNNING: 5}
        assert world.store.journal == [COMMIT]

    def test_one_sweep_takes_at_most_its_batch(self) -> None:
        world = build_memory_world()
        world.store.committed.counters = old_counters(5)
        first = sweep(world, SweepCommand(counter_batch_size=2))
        second = sweep(world, SweepCommand(counter_batch_size=2))
        assert (first.pruned_counter_count, second.pruned_counter_count) == (2, 2)
        assert len(world.store.committed.counters) == 1

    def test_nothing_due_means_nothing_committed(self) -> None:
        world = build_memory_world()
        world.store.committed.counters = {STILL_RUNNING: 5}
        assert sweep(world).pruned_counter_count == 0
        assert world.store.journal == []
        assert world.store.committed.counters == {STILL_RUNNING: 5}

    def test_the_default_batch_is_named_once(self) -> None:
        assert SweepCommand().counter_batch_size == COUNTER_PRUNE_BATCH_SIZE == 500
