"""The counter's customer lookup stands on indexes, on PostgreSQL (US-21).

A search matches a name through the trigram index of the baseline, the digits
of a phone number through the trigram index of revision 0003, and the email of
an account through the two unique indexes that lead from an address to its
profile. The digits are an expression, and the planner only uses an index on
an expression when the query writes the expression exactly as the index does,
so these ask the planner itself. Sequential scans are switched off for the
transaction, and the plan of each kind of search has to name its index.

The searches are then run through the route on the real database, where the
case blind match of a name and of an address is PostgreSQL's own and not the
in memory database's.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlalchemy import func, text
from sqlalchemy.dialects import postgresql
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.customer_search import matching_condition, search_terms
from app.infrastructure.models import Branch, CustomerProfile
from app.infrastructure.schema_ddl import (
    CUSTOMER_EMAIL_SEARCH_INDEX,
    CUSTOMER_NAME_SEARCH_INDEX,
    CUSTOMER_PHONE_SEARCH_INDEX,
)
from tests.support.booking_api import BookingClient
from tests.support.checkout_api import CUSTOMERS_PATH
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

THANDI_EMAIL: Final[str] = "thandi.mokoena@example.co.za"
ACCOUNT_KEY_INDEX: Final[str] = "customer_profile_user_account_id_key"
EXPRESSION_PIECES: Final[tuple[str, ...]] = ("gin", "gin_trgm_ops", "replace", "contact_phone")


@pytest.fixture
def branch(postgres_session: Session, postgres_factory: Factory) -> Branch:
    """Return a committed branch with a few customers registered at it."""
    built = postgres_factory.branch(code="CBD")
    thandi = postgres_factory.user(role=UserRole.CUSTOMER, email=THANDI_EMAIL)
    for name, phone, account in (
        ("Thandi Mokoena", "082 441 7719", thandi),
        ("Sipho Thandeka", "(021) 555-0142", None),
        ("Lerato Nkosi", "+27 73 228 5104", None),
    ):
        profile = postgres_factory.customer_profile(branch=built, account=account)
        profile.display_name = name
        profile.contact_phone = phone
        postgres_session.add(profile)
    postgres_session.commit()
    return built


def plan_of(session: Session, typed: str) -> str:
    """Return the plan of the count a search runs, with sequential scans switched off."""
    condition = matching_condition(search_terms(typed))
    assert condition is not None
    statement = select(func.count()).select_from(CustomerProfile).where(condition)
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    session.execute(text("SET LOCAL enable_seqscan = off"))
    rows = session.execute(text(f"EXPLAIN {sql}")).scalars().all()
    session.rollback()
    return "\n".join(str(row) for row in rows)


class TestTheIndexOfRevision0003:
    """The trigram index over the digits of the phone exists and is used."""

    def test_the_index_is_a_trigram_index_over_the_digits_of_the_phone(
        self, postgres_session: Session
    ) -> None:
        definition = postgres_session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": CUSTOMER_PHONE_SEARCH_INDEX},
        ).scalar_one()
        assert all(piece in str(definition) for piece in EXPRESSION_PIECES), definition

    def test_a_search_by_phone_stands_on_it(
        self, postgres_session: Session, branch: Branch
    ) -> None:
        assert CUSTOMER_PHONE_SEARCH_INDEX in plan_of(postgres_session, "0824417719")


class TestTheOtherTwoWaysStandOnTheBaseline:
    """A name and an email reach their profiles through indexes the baseline built."""

    def test_a_search_by_name_stands_on_the_trigram_index_of_the_name(
        self, postgres_session: Session, branch: Branch
    ) -> None:
        assert CUSTOMER_NAME_SEARCH_INDEX in plan_of(postgres_session, "Thandi")

    def test_a_search_by_email_stands_on_the_two_unique_indexes(
        self, postgres_session: Session, branch: Branch
    ) -> None:
        plan = plan_of(postgres_session, THANDI_EMAIL)
        assert CUSTOMER_EMAIL_SEARCH_INDEX in plan
        assert ACCOUNT_KEY_INDEX in plan


class TestTheSearchOnPostgres:
    """The same answers on the real database as in the fast tests."""

    @pytest.mark.parametrize(
        ("typed", "found"),
        [
            ("thand", ["Thandi Mokoena", "Sipho Thandeka"]),
            ("0824417719", ["Thandi Mokoena"]),
            ("021 5550142", ["Sipho Thandeka"]),
            ("27 73 228", ["Lerato Nkosi"]),
            (THANDI_EMAIL.upper(), ["Thandi Mokoena"]),
            ("%%", []),
        ],
    )
    def test_a_search_finds_what_it_should_in_the_order_it_should(
        self,
        booking: BookingClient,
        postgres_session: Session,
        postgres_factory: Factory,
        branch: Branch,
        typed: str,
        found: list[str],
    ) -> None:
        assistant = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
        postgres_session.commit()
        response = booking.client.get(
            CUSTOMERS_PATH, params={"q": typed}, headers=booking.headers(assistant)
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert [item["displayName"] for item in response.json()["items"]] == found
