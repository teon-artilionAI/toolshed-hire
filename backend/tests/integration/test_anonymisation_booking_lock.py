"""A new booking and an anonymisation take turns on the customer's row, on PostgreSQL (#113).

Both lock the customer profile before they decide anything. A booking that
has named its customer holds the row until it commits, so an anonymisation
of the same customer waits for it, and then finds the booking open and
refuses. An anonymisation holds the row the same way, so a booking waits, and
then finds the customer anonymised and refuses. Neither can be left half way,
with a booking pointing at a profile that names nobody.

Each waiting side is given a lock timeout of one second, so a statement that
waits fails here with SQLSTATE 55P03 instead of hanging, and the failure is
what proves it waited.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.application.booking.reservation_request import (
    CreateReservationCommand,
    RequestedLine,
    customer_named_in,
)
from app.application.identity.anonymise_customer import (
    AnonymiseCustomerCommand,
    AnonymiseCustomerUseCase,
)
from app.domain.enums import UserRole
from app.domain.errors import CustomerAnonymisedError
from app.domain.identity import Actor
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.anonymisation_world import CustomerHistory, build_customer_history
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.pg import sqlstate_of

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

LOCK_NOT_AVAILABLE: Final[str] = "55P03"
SHORT_LOCK_TIMEOUT: Final[str] = "SET lock_timeout = '1s'"
REASON: Final[str] = "The customer asked at the counter for their details to be removed."
NOW = FixedClock().now()


@pytest.fixture
def history(postgres_session: Session, postgres_factory: Factory) -> CustomerHistory:
    """Commit a customer whose hire is settled, who may be booked for or anonymised."""
    built = build_customer_history(postgres_factory)
    postgres_session.commit()
    return built


def impatient(engine: Engine) -> Callable[[], Session]:
    """Return sessions that give up on a row lock after a second instead of waiting."""

    def open_session() -> Session:
        session = Session(engine)
        session.execute(text(SHORT_LOCK_TIMEOUT))
        return session

    return open_session


def booking_for(history: CustomerHistory) -> CreateReservationCommand:
    """Return the owner's request for a draft for the customer."""
    return CreateReservationCommand(
        actor=Actor(user_id=history.owner.id, role=UserRole.ADMIN),
        branch_code=history.world.branch.code,
        start=date(2026, 3, 9),
        end=date(2026, 3, 12),
        lines=(RequestedLine(model_slug=history.world.product_model.slug, quantity=1),),
        customer_profile_id=history.world.profile.id,
    )


def anonymise(open_session: Callable[[], Session], history: CustomerHistory) -> None:
    """Anonymise the customer at the owner's request on sessions from the factory."""
    AnonymiseCustomerUseCase(SqlAlchemyUnitOfWork(open_session), FixedClock(NOW)).execute(
        AnonymiseCustomerCommand(
            actor=Actor(user_id=history.owner.id, role=UserRole.ADMIN),
            customer_profile_id=history.world.profile.id,
            reason=REASON,
        )
    )


def lock_profile_as_an_anonymisation(engine: Engine, key: UUID) -> SqlAlchemyUnitOfWork:
    """Open a unit of work that holds the profile the way an anonymisation does."""
    uow = SqlAlchemyUnitOfWork(lambda: Session(engine))
    uow.__enter__()
    assert uow.personal_data.subject_for_update(key) is not None
    return uow


class TestTheyTakeTurns:
    """Whichever holds the row first, the other waits."""

    def test_an_anonymisation_waits_for_a_booking_that_named_the_customer(
        self, postgres_engine: Engine, history: CustomerHistory
    ) -> None:
        with SqlAlchemyUnitOfWork(lambda: Session(postgres_engine)) as booking:
            customer_named_in(booking, booking_for(history))
            with pytest.raises(OperationalError) as waited:
                anonymise(impatient(postgres_engine), history)
        assert sqlstate_of(waited.value) == LOCK_NOT_AVAILABLE

    def test_a_booking_waits_for_an_anonymisation_of_its_customer(
        self, postgres_engine: Engine, history: CustomerHistory
    ) -> None:
        holder = lock_profile_as_an_anonymisation(postgres_engine, history.world.profile.id)
        try:
            with (
                SqlAlchemyUnitOfWork(impatient(postgres_engine)) as booking,
                pytest.raises(OperationalError) as waited,
            ):
                customer_named_in(booking, booking_for(history))
        finally:
            holder.__exit__(None, None, None)
        assert sqlstate_of(waited.value) == LOCK_NOT_AVAILABLE

    def test_a_booking_after_the_anonymisation_finds_the_customer_gone(
        self, postgres_engine: Engine, history: CustomerHistory
    ) -> None:
        anonymise(lambda: Session(postgres_engine), history)
        with SqlAlchemyUnitOfWork(lambda: Session(postgres_engine)) as booking:
            customer = customer_named_in(booking, booking_for(history))
        with pytest.raises(CustomerAnonymisedError):
            customer.ensure_may_book()
