"""Pruning the refresh sessions that expired long ago, and how a maintenance job ends (#90).

The pruning asks for batches until one comes back short, each with the same
cutoff ninety days before now, and logs the count of each batch and of the
run. The operator's connection string is its own setting, and a missing or
malformed one is refused naming the variable and never the value. A job that
raises is logged with its traceback and ends with a non zero status.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.application.identity.session_pruning import (
    SESSION_KEPT_AFTER_EXPIRY,
    expired_session_cutoff,
    prune_expired_sessions,
)
from app.infrastructure.session_pruning import OPERATOR_URL_VARIABLE, operator_engine
from app.jobs.job_run import EXIT_FAILURE, EXIT_SUCCESS, JobFacts, run_job
from tests.support.clock import FixedClock
from tests.support.log_capture import LogCapture

NOW = FixedClock().now()
SECRET_LOOKING_URL = "mysql://operator:do-not-print-me@db.example/toolshed"


class ScriptedStore:
    """Deletes the counts it is given, one a batch, and keeps what it was asked."""

    def __init__(self, *counts: int) -> None:
        """Keep the counts the batches answer, in order."""
        self._counts = list(counts)
        self.asked: list[tuple[datetime, int]] = []

    def delete_expired_batch(self, cutoff: datetime, limit: int) -> int:
        """Answer the next count, and keep the cutoff and the limit."""
        self.asked.append((cutoff, limit))
        return self._counts.pop(0)


class TestThePruning:
    """Batches until a short one, all against one cutoff."""

    def test_the_cutoff_is_ninety_days_before_now(self) -> None:
        assert timedelta(days=90) == SESSION_KEPT_AFTER_EXPIRY
        assert expired_session_cutoff(NOW) == NOW - timedelta(days=90)

    def test_batches_are_asked_for_until_one_comes_back_short(
        self, application_log: LogCapture
    ) -> None:
        store = ScriptedStore(3, 3, 1)
        assert prune_expired_sessions(store, NOW, batch_size=3) == 7
        assert store.asked == [(expired_session_cutoff(NOW), 3)] * 3
        assert application_log.only("sessions.pruned")["deleted_count"] == 7
        assert len(application_log.named("sessions.batch_pruned")) == 3

    def test_nothing_due_is_one_empty_batch(self) -> None:
        store = ScriptedStore(0)
        assert prune_expired_sessions(store, NOW, batch_size=500) == 0
        assert len(store.asked) == 1

    def test_a_batch_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one session"):
            prune_expired_sessions(ScriptedStore(), NOW, batch_size=0)


class TestTheOperatorConnection:
    """Its own variable, refused by name and never by value."""

    def test_an_unset_connection_string_is_refused_by_name(self) -> None:
        with pytest.raises(ValueError, match=OPERATOR_URL_VARIABLE):
            operator_engine("  ")

    def test_a_connection_string_that_is_not_postgresql_is_refused_without_its_value(
        self,
    ) -> None:
        with pytest.raises(ValueError, match=OPERATOR_URL_VARIABLE) as refused:
            operator_engine(SECRET_LOOKING_URL)
        assert "do-not-print-me" not in str(refused.value)


class TestAJobRun:
    """The exit status and the log of a job."""

    def test_a_job_that_finishes_logs_its_facts_and_exits_zero(
        self, application_log: LogCapture
    ) -> None:
        def work() -> JobFacts:
            return {"deleted_count": 4}

        assert run_job("example", work) == EXIT_SUCCESS
        finished = application_log.only("job.finished")
        assert (finished["job"], finished["deleted_count"]) == ("example", 4)

    def test_a_job_that_raises_is_logged_and_exits_non_zero(
        self, application_log: LogCapture
    ) -> None:
        def work() -> JobFacts:
            raise RuntimeError("the database went away")

        assert run_job("example", work) == EXIT_FAILURE
        failed = application_log.only("job.failed")
        assert (failed["job"], failed["error_type"]) == ("example", "RuntimeError")
