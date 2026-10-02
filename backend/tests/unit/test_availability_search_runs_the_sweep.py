"""An availability search lapses expired holds before it answers (BR-13).

A hold that has run out still occupies its units until something lapses it,
and nothing does that on a timer. A visitor who searches must not be told a
unit is taken when nobody is holding it any longer, so the search is handed
the sweep and runs it first.

These tests pin the order. The sweep runs before the availability port is
asked, once for each question, and a question that is refused never runs it,
because a refused question is answered from the request alone.

The fakes are the ones tests/unit/test_read_side_rules.py already uses. That
the sweep really frees a unit for a search is proved against PostgreSQL in
tests/integration/test_hold_expiry_sweep.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final

import pytest

from app.application.availability.read_models import AvailabilityPage, AvailabilitySearch
from app.application.availability.search import SearchAvailability
from app.application.catalogue.read_models import ModelSearch
from app.domain.errors import NotFound, ValidationFailure
from tests.support.clock import FixedClock
from tests.unit.test_read_side_rules import RAMMER, FakeAvailability, FakeBranches, FakeCatalogue

SWEEP: Final[str] = "sweep"
QUERY: Final[str] = "query"
NINTH: Final[date] = date(2026, 3, 9)
ELEVENTH: Final[date] = date(2026, 3, 11)
YESTERDAY: Final[date] = date(2026, 3, 1)


@dataclass
class OrderedAvailability(FakeAvailability):
    """An availability port that notes when it was asked, in a shared journal."""

    journal: list[str] = field(default_factory=list)

    def search(self, search: AvailabilitySearch) -> AvailabilityPage:
        """Note the question, then answer as the fake does."""
        self.journal.append(QUERY)
        return super().search(search)


@pytest.fixture
def journal() -> list[str]:
    """Return the list the sweep and the port both write into, in the order they ran."""
    return []


@pytest.fixture
def service(journal: list[str]) -> SearchAvailability:
    """Return the search on the fakes, with a sweep that notes that it ran."""
    return SearchAvailability(
        OrderedAvailability(journal=journal),
        FakeCatalogue(),
        FakeBranches(),
        FixedClock(),
        lambda: journal.append(SWEEP),
    )


class TestTheSweepRunsBeforeTheAnswer:
    """Once for each question, and before the availability port is asked."""

    def test_a_search_across_the_catalogue_sweeps_and_then_asks(
        self, service: SearchAvailability, journal: list[str]
    ) -> None:
        service.across_catalogue(NINTH, ELEVENTH, ModelSearch())
        assert journal == [SWEEP, QUERY]

    def test_a_question_about_one_model_sweeps_before_it_is_answered(
        self, service: SearchAvailability, journal: list[str]
    ) -> None:
        service.for_model(RAMMER.slug, NINTH, ELEVENTH, 1)
        assert journal == [SWEEP]

    def test_two_questions_sweep_twice(
        self, service: SearchAvailability, journal: list[str]
    ) -> None:
        service.across_catalogue(NINTH, ELEVENTH, ModelSearch())
        service.across_catalogue(NINTH, ELEVENTH, ModelSearch())
        assert journal == [SWEEP, QUERY, SWEEP, QUERY]


class TestARefusedQuestionDoesNotSweep:
    """A question that fails its checks writes nothing and asks nothing."""

    def test_a_refused_period_does_not_run_the_sweep(
        self, service: SearchAvailability, journal: list[str]
    ) -> None:
        with pytest.raises(ValidationFailure):
            service.across_catalogue(YESTERDAY, NINTH, ModelSearch())
        assert journal == []

    def test_an_unknown_model_does_not_run_the_sweep(
        self, service: SearchAvailability, journal: list[str]
    ) -> None:
        with pytest.raises(NotFound):
            service.for_model("no-such-model", NINTH, ELEVENTH, 1)
        assert journal == []
