"""The transaction boundary of the SQL unit of work.

Commit is a call somebody has to write. Leaving the block any other way, by
falling off the end, by returning early or by an exception, rolls back
everything the block wrote. These tests pin that against the real
`SqlAlchemyUnitOfWork` on the in memory database, with real rows to lose.

They also pin who closes the session. A request lends the unit of work its
own session and closes it itself. A script or a test hands in a factory, and
then the unit of work closes what it opened.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.domain import booking as domain
from app.domain.period import BookingPeriod
from app.infrastructure.models import Reservation, ReservationLine
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking import borrowing
from tests.support.factories import Factory
from tests.support.scenarios import AllocationScenario, build_allocation_scenario

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))


class CountingSession(Session):
    """A session that counts how often it was closed."""

    close_count: int = 0

    def close(self) -> None:
        """Count the call and close as usual."""
        self.close_count += 1
        super().close()


@pytest.fixture
def scenario(session: Session, factory: Factory) -> AllocationScenario:
    """Return a committed branch, product model, unit and customer."""
    built = build_allocation_scenario(factory, FIRST_HIRE)
    session.commit()
    return built


def a_reservation_for(scenario: AllocationScenario, reference: str) -> domain.Reservation:
    """Return a held reservation aggregate with no lines, not yet stored."""
    return domain.Reservation.held(
        reference=reference,
        customer_profile_id=scenario.profile.id,
        branch_id=scenario.branch.id,
        period=FIRST_HIRE,
        created_by_user_id=scenario.customer.id,
    )


def references_in(session: Session) -> set[str]:
    """Return the reference of every stored reservation."""
    return {reservation.reference for reservation in session.exec(select(Reservation)).all()}


class TestTheTransactionBoundary:
    """Commit is a call somebody has to write. Everything else rolls back."""

    def test_work_that_is_committed_is_kept(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        with borrowing(session)() as uow:
            uow.reservations.add(a_reservation_for(scenario, "TSH-R-26-900001"))
            uow.commit()
        assert "TSH-R-26-900001" in references_in(session)

    def test_leaving_the_block_without_a_commit_discards_the_work(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        with borrowing(session)() as uow:
            uow.reservations.add(a_reservation_for(scenario, "TSH-R-26-900002"))
        assert "TSH-R-26-900002" not in references_in(session)

    def test_an_exception_inside_the_block_discards_the_work_and_is_not_swallowed(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        with (
            pytest.raises(LookupError, match="something else went wrong"),
            borrowing(session)() as uow,
        ):
            uow.reservations.add(a_reservation_for(scenario, "TSH-R-26-900003"))
            raise LookupError("something else went wrong")
        assert "TSH-R-26-900003" not in references_in(session)

    def test_an_explicit_rollback_discards_the_work_and_the_block_carries_on(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        with borrowing(session)() as uow:
            uow.reservations.add(a_reservation_for(scenario, "TSH-R-26-900004"))
            uow.rollback()
            uow.reservations.add(a_reservation_for(scenario, "TSH-R-26-900005"))
            uow.commit()
        assert references_in(session) >= {"TSH-R-26-900005"}
        assert "TSH-R-26-900004" not in references_in(session)

    def test_a_reservation_is_stored_with_its_lines(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        reservation = a_reservation_for(scenario, "TSH-R-26-900006")
        with borrowing(session)() as uow:
            model = uow.product_models.get(scenario.product_model.id)
            assert model is not None
            line = reservation.add_line(model, 2)
            uow.reservations.add(reservation)
            uow.commit()
        stored = session.get(ReservationLine, line.id)
        assert stored is not None
        assert stored.reservation_id == reservation.id
        assert stored.quantity == 2
        assert stored.daily_rate_snapshot == scenario.product_model.daily_rate

    def test_committing_outside_the_block_is_refused(self, session: Session) -> None:
        uow = borrowing(session)()
        with pytest.raises(RuntimeError, match="outside its `with` block"):
            uow.commit()
        with pytest.raises(RuntimeError, match="outside its `with` block"):
            uow.rollback()

    def test_entering_an_open_unit_of_work_again_is_refused(self, session: Session) -> None:
        uow = borrowing(session)()
        with uow, pytest.raises(RuntimeError, match="already open"):
            uow.__enter__()

    def test_a_unit_of_work_can_be_entered_again_once_it_has_been_left(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        uow = borrowing(session)()
        with uow:
            assert uow.branches.get(scenario.branch.id) is not None
        with uow:
            assert uow.branches.get(scenario.branch.id) is not None

    def test_a_session_the_unit_of_work_opened_is_closed_on_the_way_out(
        self, sqlite_engine: Engine
    ) -> None:
        opened: list[CountingSession] = []

        def open_session() -> CountingSession:
            """Open a session and keep hold of it for the assertion."""
            opened.append(CountingSession(sqlite_engine))
            return opened[-1]

        with SqlAlchemyUnitOfWork(open_session):
            pass
        assert [session.close_count for session in opened] == [1]

    def test_a_borrowed_session_is_left_open_for_its_owner(self, sqlite_engine: Engine) -> None:
        borrowed = CountingSession(sqlite_engine)
        with SqlAlchemyUnitOfWork(lambda: borrowed, close_on_exit=False):
            pass
        assert borrowed.close_count == 0
        borrowed.close()
