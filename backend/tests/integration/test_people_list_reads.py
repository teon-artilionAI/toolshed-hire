"""The reads of the people screens on PostgreSQL, the statements each takes and how each is planned.

A page of the staff is two statements however many accounts the business has,
and one staff account is one. A page of the customers by standing is two. The
lock every change to a staff account takes on the active administrators is
one. None of them walks a whole table to find what it wants. With sequential
scans switched off, a plan names a sequential scan only when no index can
serve the statement, so each plan is asked for one with the rows of a busy
business in place. The plans are worked out in a transaction that is rolled
back, so the statistics never reach another test.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.application.identity.customer_listing import CustomerListSearch
from app.application.identity.staff_read_models import StaffSearch
from app.domain.enums import AccountStatus, UserRole
from app.infrastructure.customer_listing import SqlCustomerListing
from app.infrastructure.staff_accounts import SqlStaffRepository
from app.infrastructure.staff_query import SqlStaffDirectory
from tests.support.factories import Factory
from tests.support.people_pg import WALKING_THE_TABLE, plans_of, stock_people
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

FEW: Final[int] = 3
MANY: Final[int] = 80
LIST_STATEMENTS: Final[int] = 2
ONE_STATEMENT: Final[int] = 1
STAFF_ACCOUNTS: Final[int] = 3
# A plan node that sorts rows, which a page read off an index in its order needs none of.
SORTED: Final[str] = "Sort"


def staff_search(**changes: object) -> StaffSearch:
    """Return a search of the staff for one page of twenty."""
    values: dict[str, object] = {
        "text": None,
        "role": None,
        "active": None,
        "page": 1,
        "page_size": 20,
        **changes,
    }
    return StaffSearch(**values)


def customer_search(**changes: object) -> CustomerListSearch:
    """Return a list of customers for one page of twenty."""
    values: dict[str, object] = {"status": None, "text": None, "page": 1, "page_size": 20}
    return CustomerListSearch(**{**values, **changes})


class TestTheStatementsDoNotGrowWithTheRows:
    """Each read takes the same statements however many customers the business has."""

    @pytest.mark.parametrize("customers", [FEW, MANY])
    def test_a_page_of_staff_is_two_statements_and_holds_no_customer(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        customers: int,
    ) -> None:
        people = stock_people(postgres_session, postgres_factory, customers)
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as sent:
            page = SqlStaffDirectory(reader).page(staff_search())
        assert (page.total, len(sent)) == (STAFF_ACCOUNTS, LIST_STATEMENTS)
        assert {member.role for member in page.items} == {
            UserRole.ADMIN,
            UserRole.COUNTER_STAFF,
        }
        branch_codes = {member.branch_code for member in page.items}
        assert branch_codes == {None, people.branch.code}

    def test_one_staff_account_is_one_statement_and_a_customer_is_none(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        people = stock_people(postgres_session, postgres_factory, FEW)
        customer = postgres_factory.user(role=UserRole.CUSTOMER)
        postgres_session.commit()
        assistant_id, customer_id = people.assistant.id, customer.id
        with Session(postgres_engine) as reader:
            directory = SqlStaffDirectory(reader)
            with recorded_statements(postgres_engine) as sent:
                member = directory.one(assistant_id)
            assert directory.one(customer_id) is None
        assert member is not None
        assert (member.role, member.branch_code, len(sent)) == (
            UserRole.COUNTER_STAFF,
            people.branch.code,
            ONE_STATEMENT,
        )

    @pytest.mark.parametrize("customers", [FEW, MANY])
    def test_a_page_of_customers_by_standing_is_two_statements(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        customers: int,
    ) -> None:
        stock_people(postgres_session, postgres_factory, customers)
        held = (customers + 9) // 10
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as sent:
            page = SqlCustomerListing(reader).page(customer_search(status=AccountStatus.ON_HOLD))
        assert (page.total, len(sent)) == (held, LIST_STATEMENTS)
        assert {summary.account_status for summary in page.items} == {AccountStatus.ON_HOLD}

    def test_the_lock_on_the_administrators_is_one_statement(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        people = stock_people(postgres_session, postgres_factory, MANY)
        with Session(postgres_engine) as writer, recorded_statements(postgres_engine) as sent:
            locked = SqlStaffRepository(writer).lock_active_administrators()
            writer.rollback()
        assert locked == {people.owner.id, people.bookkeeper.id}
        assert len(sent) == ONE_STATEMENT


class TestNoReadWalksAWholeTable:
    """Every statement of every read is served by an index, with many customers in place."""

    @pytest.fixture
    def stocked(self, postgres_session: Session, postgres_factory: Factory) -> None:
        """Commit a business with many customers and three staff."""
        stock_people(postgres_session, postgres_factory, MANY)

    @pytest.mark.parametrize(
        "search",
        [
            staff_search(),
            staff_search(role=UserRole.ADMIN),
            staff_search(active=True, text="adonis"),
        ],
    )
    def test_the_staff_are_read_without_walking_every_account(
        self, postgres_engine: Engine, stocked: None, search: StaffSearch
    ) -> None:
        plans = plans_of(postgres_engine, lambda session: SqlStaffDirectory(session).page(search))
        assert len(plans) == LIST_STATEMENTS
        for plan in plans:
            assert WALKING_THE_TABLE not in plan, plan

    def test_the_lock_on_the_administrators_does_not_walk_every_account(
        self, postgres_engine: Engine, stocked: None
    ) -> None:
        (plan,) = plans_of(
            postgres_engine,
            lambda session: SqlStaffRepository(session).lock_active_administrators(),
        )
        assert WALKING_THE_TABLE not in plan, plan

    @pytest.mark.parametrize(
        "search",
        [
            customer_search(status=AccountStatus.ON_HOLD),
            customer_search(status=AccountStatus.BLACKLISTED),
            customer_search(text="zungu"),
            customer_search(text="customer0004@example.co.za", status=AccountStatus.ACTIVE),
        ],
    )
    def test_the_customers_out_of_good_standing_or_searched_for_are_found_by_index(
        self, postgres_engine: Engine, stocked: None, search: CustomerListSearch
    ) -> None:
        plans = plans_of(postgres_engine, lambda session: SqlCustomerListing(session).page(search))
        assert len(plans) == LIST_STATEMENTS
        for plan in plans:
            assert WALKING_THE_TABLE not in plan, plan

    @pytest.mark.parametrize(
        "search", [customer_search(), customer_search(status=AccountStatus.ACTIVE)]
    )
    def test_a_page_of_every_customer_is_read_in_name_order_off_an_index(
        self, postgres_engine: Engine, stocked: None, search: CustomerListSearch
    ) -> None:
        _, page_plan = plans_of(
            postgres_engine, lambda session: SqlCustomerListing(session).page(search)
        )
        assert WALKING_THE_TABLE not in page_plan, page_plan
        assert SORTED not in page_plan, page_plan
