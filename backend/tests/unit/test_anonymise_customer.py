"""The owner's request and the monthly job, each anonymising through the same steps (#113).

A request anonymises one customer with a reason the audit event keeps, ends
the account's sessions and answers the customer as the counter now reads
them. It refuses a reason out of bounds, an unknown customer, one anonymised
already and one with anything open, and writes nothing when it does.

The job reads a page of dormant customers and anonymises it in one
transaction, skipping one that no longer qualifies once read again, with no
actor and the schedule as the trigger. In report mode it writes nothing. A run
goes a page at a time until a page comes back short.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from app.application.identity.anonymise_customer import (
    CUSTOMER_ANONYMISED_ACTION,
    AnonymiseCustomerCommand,
    AnonymiseCustomerUseCase,
)
from app.application.identity.anonymise_dormant import (
    AnonymiseDormantCustomersUseCase,
    DormantBatchCommand,
)
from app.domain.anonymisation import (
    ANONYMISED_DISPLAY_NAME,
    OpenMatters,
    anonymised_email,
    dormancy_cutoff,
)
from app.domain.enums import RevokeReason, UserRole
from app.domain.errors import NotFound, StateTransitionError, ValidationFailure
from app.domain.identity import Actor
from app.jobs.anonymise_customers import anonymise_dormant_customers
from tests.support.clock import FixedClock
from tests.support.log_capture import LogCapture
from tests.support.memory_anonymisation import (
    ERASED_ROWS,
    AnonymisationStore,
    MemoryAnonymisationUnitOfWork,
)

OWNER = Actor(user_id=uuid4(), role=UserRole.ADMIN)
REASON = "The customer asked by email for their details to be removed."
NOW = FixedClock().now()
CUTOFF = dormancy_cutoff(NOW)


def request(store: AnonymisationStore, key: UUID, reason: str = REASON) -> object:
    """Anonymise a customer at the owner's request."""
    use_case = AnonymiseCustomerUseCase(MemoryAnonymisationUnitOfWork(store), FixedClock())
    return use_case.execute(
        AnonymiseCustomerCommand(actor=OWNER, customer_profile_id=key, reason=reason)
    )


def page(
    store: AnonymisationStore,
    *,
    after: UUID | None = None,
    report_only: bool = False,
    size: int = 100,
) -> object:
    """Run one page of the monthly job."""
    use_case = AnonymiseDormantCustomersUseCase(MemoryAnonymisationUnitOfWork(store), FixedClock())
    return use_case.execute(
        DormantBatchCommand(cutoff=CUTOFF, after=after, batch_size=size, report_only=report_only)
    )


class TestTheOwnersRequest:
    """One customer, one transaction, one event."""

    def test_the_customer_is_anonymised_and_the_event_keeps_the_reason(self) -> None:
        key, account = uuid4(), uuid4()
        store = AnonymisationStore()
        store.add(key=key, account=account)
        summary = request(store, key)
        assert summary.display_name == ANONYMISED_DISPLAY_NAME
        assert summary.email == anonymised_email(key)
        assert summary.anonymised_at == NOW
        assert store.committed.revoked == [(account, RevokeReason.ADMIN_REVOKE)]
        (event,) = store.committed.events
        assert (event.action, event.entity_id, event.actor_user_id) == (
            CUSTOMER_ANONYMISED_ACTION,
            key,
            OWNER.user_id,
        )
        assert event.before_state is None
        assert event.after_state == {
            "trigger": "request",
            "reason": REASON,
            "sessions": ERASED_ROWS.sessions,
            "bookings": ERASED_ROWS.bookings,
            "hire_items": ERASED_ROWS.hire_items,
            "damage_reports": 0,
            "charges": 0,
            "notifications": 0,
            "sessions_revoked": 1,
        }

    def test_a_walk_in_has_no_account_and_no_session_to_revoke(self) -> None:
        key = uuid4()
        store = AnonymisationStore()
        store.add(key=key)
        summary = request(store, key)
        assert (summary.email, store.committed.revoked) == (None, [])
        assert store.known(key).account is None

    @pytest.mark.parametrize("reason", ["", "Gone", "x" * 201])
    def test_a_reason_out_of_bounds_is_refused_and_nothing_is_written(self, reason: str) -> None:
        key = uuid4()
        store = AnonymisationStore()
        store.add(key=key)
        with pytest.raises(ValidationFailure):
            request(store, key, reason)
        assert store.journal == []

    def test_a_customer_nobody_registered_is_not_found(self) -> None:
        with pytest.raises(NotFound):
            request(AnonymisationStore(), uuid4())

    def test_a_customer_anonymised_already_is_refused(self) -> None:
        key = uuid4()
        store = AnonymisationStore()
        store.add(key=key)
        request(store, key)
        with pytest.raises(StateTransitionError):
            request(store, key)
        assert len(store.committed.events) == 1

    def test_a_customer_with_a_hire_owing_is_refused_and_nothing_is_written(self) -> None:
        key = uuid4()
        store = AnonymisationStore()
        store.add(key=key, account=uuid4(), matters=OpenMatters(hires_owing=1))
        with pytest.raises(StateTransitionError):
            request(store, key)
        assert store.journal == []
        assert store.known(key).subject.anonymised_at is None


class TestTheMonthlyJob:
    """A page in one transaction, the schedule as the trigger, nothing in report mode."""

    def test_a_page_is_anonymised_with_no_actor_and_the_schedule_named(self) -> None:
        store = AnonymisationStore()
        keys = sorted(uuid4() for _ in range(3))
        for key in keys:
            store.add(key=key, dormant=True)
        batch = page(store)
        assert batch.found == tuple(keys) == batch.anonymised
        assert store.journal == ["commit"]
        assert {event.actor_user_id for event in store.committed.events} == {None}
        assert {event.after_state["trigger"] for event in store.committed.events} == {"schedule"}
        assert all("reason" not in event.after_state for event in store.committed.events)

    def test_report_mode_finds_the_page_and_writes_nothing(self) -> None:
        store = AnonymisationStore()
        key = uuid4()
        store.add(key=key, dormant=True)
        batch = page(store, report_only=True)
        assert (batch.found, batch.anonymised) == ((key,), ())
        assert store.journal == []
        assert store.known(key).subject.anonymised_at is None

    def test_one_that_no_longer_qualifies_is_skipped_and_the_rest_go_ahead(
        self, application_log: LogCapture
    ) -> None:
        store = AnonymisationStore()
        booked, signed_in, dormant = sorted(uuid4() for _ in range(3))
        store.add(key=booked, matters=OpenMatters(open_bookings=1), dormant=True)
        store.add(
            key=signed_in,
            account=uuid4(),
            last_signed_in_at=NOW - timedelta(days=1),
            dormant=True,
        )
        store.add(key=dormant, dormant=True)
        batch = page(store)
        assert batch.anonymised == (dormant,)
        assert set(batch.skipped) == {booked, signed_in}
        skipped = application_log.named("anonymisation.customer_skipped")
        assert {entry["customer_profile_id"] for entry in skipped} == {str(booked), str(signed_in)}

    def test_a_run_goes_a_page_at_a_time_until_a_page_comes_back_short(self) -> None:
        store = AnonymisationStore()
        for _ in range(5):
            store.add(key=uuid4(), dormant=True)
        totals = anonymise_dormant_customers(
            lambda: MemoryAnonymisationUnitOfWork(store),
            FixedClock(),
            report_only=False,
            batch_size=2,
        )
        assert (totals.pages, totals.found, totals.anonymised, totals.skipped) == (3, 5, 5, 0)
        assert store.journal == ["commit"] * 3

    def test_a_report_run_reads_every_page_and_writes_nothing(self) -> None:
        store = AnonymisationStore()
        for _ in range(4):
            store.add(key=uuid4(), dormant=True)
        totals = anonymise_dormant_customers(
            lambda: MemoryAnonymisationUnitOfWork(store),
            FixedClock(),
            report_only=True,
            batch_size=2,
        )
        assert (totals.pages, totals.found, totals.anonymised) == (3, 4, 0)
        assert store.journal == []

    def test_a_batch_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one customer"):
            page(AnonymisationStore(), size=0)

