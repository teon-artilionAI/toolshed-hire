"""Adding and cancelling a closure day, run against ports and nothing else (B9.5, BR-49, BR-51).

Adding one holds the reason and the day to the domain's rules, looks the
branch up among those still trading, and refuses a day that is closed already
at that branch or at every branch, whether its own check finds it or the unique
index does. Cancelling one stamps it and keeps it. Each change commits with its
audit event or commits nothing, and every refusal names its field the way the
request did. The unit of work is the in memory double of
tests/support/memory_closures.py, on the still clock's Monday 2 March 2026.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.refusal import refused_parameter_of
from app.application.trading.closure_days import (
    CLOSURE_ADDED_ACTION,
    CLOSURE_CANCELLED_ACTION,
    AddClosureDayCommand,
    AddClosureDayUseCase,
    CancelClosureDayCommand,
    CancelClosureDayUseCase,
)
from app.domain.closure_day import CLOSURE_REASON_MAX_LENGTH, FURTHEST_CLOSURE_DAYS, ClosureDay
from app.domain.errors import NotFound, StateTransitionError, ValidationFailure
from tests.support.catalogue_terms import ADMINISTRATOR
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.memory_closures import (
    COMMIT,
    ClosureStore,
    MemoryClosureUnitOfWork,
    StoreFault,
)

TODAY = date(2026, 3, 2)
STOCKTAKE_DAY = date(2026, 3, 20)
STOCKTAKE = "Stocktake"
ELECTION_DAY = "Election day, declared by the government"


@pytest.fixture
def store() -> ClosureStore:
    """Return a store with two trading branches, CBD and BEL."""
    built = ClosureStore()
    built.branch("CBD")
    built.branch("BEL")
    return built


def add(
    store: ClosureStore,
    *,
    branch_code: str | None = "CBD",
    day: date = STOCKTAKE_DAY,
    reason: str = STOCKTAKE,
) -> ClosureDay:
    """Add a closure through the use case on the still clock."""
    use_case = AddClosureDayUseCase(MemoryClosureUnitOfWork(store), FixedClock())
    return use_case.execute(
        AddClosureDayCommand(actor=ADMINISTRATOR, branch_code=branch_code, day=day, reason=reason)
    )


def cancel(store: ClosureStore, closure_id: UUID) -> ClosureDay:
    """Cancel a closure through the use case on the still clock."""
    use_case = CancelClosureDayUseCase(MemoryClosureUnitOfWork(store), FixedClock())
    return use_case.execute(CancelClosureDayCommand(actor=ADMINISTRATOR, closure_id=closure_id))


def refused_field(error: pytest.ExceptionInfo[ValidationFailure]) -> str | None:
    """Return the field a refusal names."""
    return refused_parameter_of(error.value)


class TestAddingAClosure:
    """A closure is kept with its audit event, for one branch or every branch."""

    def test_a_closure_of_one_branch_is_kept_with_its_audit_event(
        self, store: ClosureStore
    ) -> None:
        closure = add(store, reason="  Stocktake  ")

        assert closure.branch_code == "CBD"
        assert closure.branch_id == store.branches["CBD"].id
        assert (closure.day, closure.reason, closure.is_live) == (STOCKTAKE_DAY, STOCKTAKE, True)
        assert closure.created_at == DEFAULT_INSTANT
        assert store.committed.closures == {closure.id: closure}
        assert store.committed.created_by[closure.id] == ADMINISTRATOR.user_id
        (event,) = store.events
        assert (event.action, event.entity_type, event.entity_id) == (
            CLOSURE_ADDED_ACTION,
            "closure_day",
            closure.id,
        )
        assert event.before_state is None
        assert event.after_state == {
            "branch_code": "CBD",
            "day": "2026-03-20",
            "reason": STOCKTAKE,
        }
        assert event.actor_user_id == ADMINISTRATOR.user_id
        assert store.journal == [COMMIT]

    def test_a_closure_of_every_branch_names_no_branch(self, store: ClosureStore) -> None:
        closure = add(store, branch_code=None, reason=ELECTION_DAY)

        assert (closure.branch_id, closure.branch_code) == (None, None)
        assert store.events[0].after_state == {
            "branch_code": None,
            "day": "2026-03-20",
            "reason": ELECTION_DAY,
        }

    @pytest.mark.parametrize(
        "day", [TODAY, TODAY + timedelta(days=FURTHEST_CLOSURE_DAYS)], ids=["today", "a-year-on"]
    )
    def test_today_and_the_last_day_a_year_on_may_close(
        self, store: ClosureStore, day: date
    ) -> None:
        assert add(store, day=day).day == day

    def test_a_day_one_branch_has_closed_may_still_close_for_every_branch(
        self, store: ClosureStore
    ) -> None:
        store.keep(branch_code="CBD", day=STOCKTAKE_DAY)

        closure = add(store, branch_code=None, reason=ELECTION_DAY)

        assert closure.branch_code is None
        assert len(store.committed.closures) == 2

    def test_a_cancelled_closure_does_not_hold_the_day(self, store: ClosureStore) -> None:
        first = add(store)
        cancel(store, first.id)

        second = add(store)

        assert second.id != first.id
        assert second.is_live


class TestRefusingAClosure:
    """A refusal names its field, or is a conflict, and writes nothing."""

    @pytest.mark.parametrize(
        "reason", ["", "   ", "x" * (CLOSURE_REASON_MAX_LENGTH + 1)], ids=["empty", "blank", "long"]
    )
    def test_a_reason_out_of_bounds_is_refused_naming_it(
        self, store: ClosureStore, reason: str
    ) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            add(store, reason=reason)

        assert refused_field(refusal) == "reason"
        assert store.journal == []

    @pytest.mark.parametrize(
        ("day", "words"),
        [
            (TODAY - timedelta(days=1), "has passed"),
            (TODAY + timedelta(days=FURTHEST_CLOSURE_DAYS + 1), "at most 366 days"),
        ],
        ids=["yesterday", "beyond-a-year"],
    )
    def test_a_day_out_of_reach_is_refused_naming_it(
        self, store: ClosureStore, day: date, words: str
    ) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            add(store, day=day)

        assert refused_field(refusal) == "day"
        assert words in refusal.value.message
        assert store.committed.closures == {}

    @pytest.mark.parametrize("code", ["NOPE", "OLD"], ids=["unknown", "no-longer-trading"])
    def test_a_branch_that_is_not_trading_is_refused_naming_it(
        self, store: ClosureStore, code: str
    ) -> None:
        store.branch("OLD")
        store.closed_branch_codes.add("OLD")

        with pytest.raises(ValidationFailure) as refusal:
            add(store, branch_code=code)

        assert refused_field(refusal) == "branchCode"
        assert store.journal == []

    def test_a_second_closure_of_the_branch_that_day_is_a_conflict_naming_the_first(
        self, store: ClosureStore
    ) -> None:
        store.keep(branch_code="CBD", day=STOCKTAKE_DAY, reason="Annual count")

        with pytest.raises(StateTransitionError) as refusal:
            add(store)

        assert refusal.value.message == (
            "CBD is already closed on Friday 20 March 2026 (Annual count). "
            "Cancel that closure first."
        )
        assert len(store.committed.closures) == 1
        assert store.journal == []

    @pytest.mark.parametrize("branch_code", ["CBD", None], ids=["one-branch", "every-branch"])
    def test_a_day_every_branch_is_closed_refuses_another_closure(
        self, store: ClosureStore, branch_code: str | None
    ) -> None:
        store.keep(branch_code=None, day=STOCKTAKE_DAY, reason=ELECTION_DAY)

        with pytest.raises(StateTransitionError) as refusal:
            add(store, branch_code=branch_code)

        assert refusal.value.message.startswith("Every branch is already closed on Friday 20")

    def test_another_branch_closed_that_day_does_not_refuse_this_one(
        self, store: ClosureStore
    ) -> None:
        store.keep(branch_code="BEL", day=STOCKTAKE_DAY)

        assert add(store, branch_code="CBD").branch_code == "CBD"

    def test_a_race_lost_to_the_unique_index_is_the_same_conflict(
        self, store: ClosureStore
    ) -> None:
        store.race_on_add = True

        with pytest.raises(StateTransitionError) as refusal:
            add(store)

        assert "already closed on Friday 20 March 2026" in refusal.value.message
        assert store.committed.closures == {}

    def test_a_failed_audit_write_keeps_nothing(self, store: ClosureStore) -> None:
        store.fail_audit = True

        with pytest.raises(StoreFault):
            add(store)

        assert store.committed.closures == {}
        assert store.journal == []


class TestCancellingAClosure:
    """A cancellation stamps the closure and keeps it, with its audit event (BR-51)."""

    def test_a_live_closure_is_cancelled_and_kept(self, store: ClosureStore) -> None:
        kept = store.keep(branch_code="CBD", day=STOCKTAKE_DAY)

        cancelled = cancel(store, kept.id)

        assert cancelled.cancelled_at == DEFAULT_INSTANT
        assert not cancelled.is_live
        assert store.committed.closures[kept.id] == cancelled
        assert store.committed.cancelled_by[kept.id] == ADMINISTRATOR.user_id
        (event,) = store.events
        assert (event.action, event.entity_id) == (CLOSURE_CANCELLED_ACTION, kept.id)
        assert event.before_state == {"state": "live"}
        assert event.after_state == {
            "state": "cancelled",
            "branch_code": "CBD",
            "day": "2026-03-20",
            "reason": STOCKTAKE,
        }

    def test_an_unknown_closure_is_not_found(self, store: ClosureStore) -> None:
        with pytest.raises(NotFound):
            cancel(store, uuid4())

        assert store.journal == []

    def test_a_closure_cancelled_already_is_a_conflict(self, store: ClosureStore) -> None:
        kept = store.keep(branch_code=None, day=STOCKTAKE_DAY)
        cancel(store, kept.id)

        with pytest.raises(StateTransitionError) as refusal:
            cancel(store, kept.id)

        assert refusal.value.message == "This closure was cancelled already."
        assert store.journal == [COMMIT]
        assert len(store.events) == 1
