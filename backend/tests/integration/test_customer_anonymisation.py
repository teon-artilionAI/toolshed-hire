"""Anonymising customers on PostgreSQL, by request and by the monthly job (#113).

The job's candidates are read from rows back dated past and short of the two
years. A customer whose last hire was settled three years ago and who has not
signed in since qualifies, and so does a walk-in registered three years ago
who never hired. A customer whose hire ended last year does not, nor one whose
old hire still owes money, nor one who signed in last month, nor one
registered last month, nor one anonymised already.

The job runs as the restricted application role, which may update the rows it
writes over and insert the audit events, and may not touch an event once
written. In report mode it reads the same customers and changes nothing. A
real run anonymises exactly them, with one event each naming the schedule, and
the next run finds nobody.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, col, select

from app.application.identity.anonymise_customer import (
    CUSTOMER_ANONYMISED_ACTION,
    AnonymiseCustomerCommand,
    AnonymiseCustomerUseCase,
)
from app.domain.anonymisation import ANONYMISED_DISPLAY_NAME, dormancy_cutoff
from app.domain.enums import RentalStatus, UserRole
from app.domain.errors import StateTransitionError
from app.domain.identity import Actor
from app.infrastructure.models import AuditEvent, CustomerProfile, Rental, UserAccount
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.jobs.anonymise_customers import anonymise_dormant_customers
from tests.support.anonymisation_world import build_customer_history
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    INSUFFICIENT_PRIVILEGE_SQLSTATE,
    engine_as,
    provision_restricted_roles,
    sqlstate_of_refusal,
)

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

NOW = FixedClock().now()
CUTOFF = dormancy_cutoff(NOW)
THREE_YEARS_AGO = NOW - timedelta(days=3 * 365)
LAST_YEAR = NOW - timedelta(days=365)
LAST_MONTH = NOW - timedelta(days=30)
SMALL_BATCH: Final[int] = 2
REASON: Final[str] = "The customer asked at the counter for their details to be removed."


@pytest.fixture(scope="module")
def application_engine(postgres_engine: Engine, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the restricted application role."""
    provision_restricted_roles(postgres_engine, postgres_url)
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def customers(postgres_session: Session, postgres_factory: Factory) -> dict[str, UUID]:
    """Commit a customer of each kind the job has to tell apart, by what they are."""
    owner = postgres_factory.user(role=UserRole.ADMIN)
    dormant = build_customer_history(postgres_factory, ended_at=THREE_YEARS_AGO, with_owner=owner)
    recent = build_customer_history(postgres_factory, ended_at=LAST_YEAR, with_owner=owner)
    owing = build_customer_history(
        postgres_factory,
        ended_at=THREE_YEARS_AGO,
        rental_status=RentalStatus.RETURNED,
        balance_due=Decimal("80.00"),
        with_owner=owner,
    )
    signed_in = build_customer_history(
        postgres_factory, ended_at=THREE_YEARS_AGO, with_owner=owner
    )
    signed_in.world.customer.last_login_at = LAST_MONTH
    postgres_session.add(signed_in.world.customer)
    old_walk_in = postgres_factory.customer_profile(branch=dormant.world.branch)
    old_walk_in.created_at = THREE_YEARS_AGO
    new_walk_in = postgres_factory.customer_profile(branch=dormant.world.branch)
    new_walk_in.created_at = LAST_MONTH
    gone = postgres_factory.customer_profile(branch=dormant.world.branch)
    gone.created_at = THREE_YEARS_AGO
    gone.anonymised_at = LAST_YEAR
    postgres_session.add_all([old_walk_in, new_walk_in, gone])
    postgres_session.commit()
    return {
        "owner": owner.id,
        "dormant": dormant.world.profile.id,
        "recent": recent.world.profile.id,
        "owing": owing.world.profile.id,
        "signed_in": signed_in.world.profile.id,
        "old_walk_in": old_walk_in.id,
        "new_walk_in": new_walk_in.id,
        "gone": gone.id,
    }


def run(engine: Engine, *, report_only: bool) -> tuple[int, int]:
    """Run the whole job on the engine, a small page at a time, and return found and done."""
    totals = anonymise_dormant_customers(
        lambda: SqlAlchemyUnitOfWork(lambda: Session(engine)),
        FixedClock(NOW),
        report_only=report_only,
        batch_size=SMALL_BATCH,
    )
    return totals.found, totals.anonymised


def names(engine: Engine) -> dict[UUID, str]:
    """Return the name every profile holds now, by key."""
    with Session(engine) as session:
        rows = session.exec(select(CustomerProfile.id, CustomerProfile.display_name)).all()
    return dict(rows)


def anonymised_events(engine: Engine) -> list[AuditEvent]:
    """Return every anonymisation event, oldest first."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(AuditEvent)
                .where(col(AuditEvent.action) == CUSTOMER_ANONYMISED_ACTION)
                .order_by(col(AuditEvent.id))
            ).all()
        )


class TestWhoTheJobFinds:
    """The two years, measured on back dated rows."""

    def test_only_the_dormant_customer_and_the_old_walk_in_qualify(
        self, postgres_engine: Engine, customers: dict[str, UUID]
    ) -> None:
        with Session(postgres_engine) as session:
            uow = SqlAlchemyUnitOfWork(lambda: session, close_on_exit=False)
            with uow:
                found = uow.personal_data.dormant_customers(CUTOFF, after=None, limit=100)
        assert set(found) == {customers["dormant"], customers["old_walk_in"]}
        assert list(found) == sorted(found)


class TestTheJob:
    """Report first, then the run, as the application role."""

    def test_report_mode_finds_them_and_changes_nothing(
        self, postgres_engine: Engine, application_engine: Engine, customers: dict[str, UUID]
    ) -> None:
        before = names(postgres_engine)
        assert run(application_engine, report_only=True) == (2, 0)
        assert names(postgres_engine) == before
        assert anonymised_events(postgres_engine) == []

    def test_a_run_anonymises_exactly_them_and_the_next_finds_nobody(
        self, postgres_engine: Engine, application_engine: Engine, customers: dict[str, UUID]
    ) -> None:
        assert run(application_engine, report_only=False) == (2, 2)
        after = names(postgres_engine)
        taken = {customers["dormant"], customers["old_walk_in"]}
        assert {key for key, name in after.items() if name == ANONYMISED_DISPLAY_NAME} == taken
        events = anonymised_events(postgres_engine)
        assert {event.entity_id for event in events} == taken
        assert {(event.actor_user_id, event.after_state["trigger"]) for event in events} == {
            (None, "schedule")
        }
        with Session(postgres_engine) as session:
            account = session.exec(
                select(UserAccount)
                .join(CustomerProfile, col(CustomerProfile.user_account_id) == col(UserAccount.id))
                .where(col(CustomerProfile.id) == customers["dormant"])
            ).one()
            hires = session.exec(select(Rental)).all()
        assert account.is_active is False
        assert len(hires) == 4
        assert run(application_engine, report_only=False) == (0, 0)

    def test_the_application_role_cannot_rewrite_the_event_it_wrote(
        self, application_engine: Engine, customers: dict[str, UUID]
    ) -> None:
        run(application_engine, report_only=False)
        with application_engine.connect() as connection, pytest.raises(DBAPIError) as refused:
            connection.execute(
                text("UPDATE audit_event SET after_state = NULL WHERE action = :action"),
                {"action": CUSTOMER_ANONYMISED_ACTION},
            )
        assert sqlstate_of_refusal(refused.value) == INSUFFICIENT_PRIVILEGE_SQLSTATE


class TestTheOwnersRequest:
    """The request on the real database, as the application role."""

    def test_an_owner_anonymises_a_recent_customer_and_cannot_twice(
        self, application_engine: Engine, customers: dict[str, UUID]
    ) -> None:
        use_case = AnonymiseCustomerUseCase(
            SqlAlchemyUnitOfWork(lambda: Session(application_engine)), FixedClock(NOW)
        )
        command = AnonymiseCustomerCommand(
            actor=Actor(user_id=customers["owner"], role=UserRole.ADMIN),
            customer_profile_id=customers["recent"],
            reason=REASON,
        )
        assert use_case.execute(command).display_name == ANONYMISED_DISPLAY_NAME
        with pytest.raises(StateTransitionError):
            use_case.execute(command)

    def test_a_hire_still_owing_is_refused(
        self, application_engine: Engine, customers: dict[str, UUID]
    ) -> None:
        use_case = AnonymiseCustomerUseCase(
            SqlAlchemyUnitOfWork(lambda: Session(application_engine)), FixedClock(NOW)
        )
        with pytest.raises(StateTransitionError, match="a hire not yet settled"):
            use_case.execute(
                AnonymiseCustomerCommand(
                    actor=Actor(user_id=customers["owner"], role=UserRole.ADMIN),
                    customer_profile_id=customers["owing"],
                    reason=REASON,
                )
            )
