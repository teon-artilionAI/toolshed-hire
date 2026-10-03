"""The counter looking a customer up, through HTTP (US-21).

Staff find a customer by part of a name, by a phone number however it is
punctuated, or by the email address of their account, best match first, a page
at a time, and open one by its key. These pin the shape of `CustomerSummary`,
each way of matching, the order, the paging and every refusal of the text.

Who may call the three customer routes is pinned in
tests/api/test_route_policies.py. These run against the in memory database.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.domain.enums import CustomerType, UserRole
from app.infrastructure.models import Branch, CustomerProfile, UserAccount
from tests.support.checkout_api import CUSTOMERS_PATH, customer_path
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.tokens import authorization_header, mint_access_token

SUMMARY_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "displayName", "email", "phone", "hasLogin", "emailVerified", "customerType",
        "companyName", "idDocumentType", "idDocumentLast4", "billingSuburb", "billingCity",
        "accountStatus", "tradeDiscountPercent", "noShowCount", "homeBranchCode",
    }
)  # fmt: skip
PAGE_MEMBERS: Final[frozenset[str]] = frozenset({"items", "page", "pageSize", "total"})
THANDI_EMAIL: Final[str] = "thandi.mokoena@example.co.za"
VALIDATION_PROBLEM: Final[str] = "request-validation-failure"


@pytest.fixture
def branch(session: Session, factory: Factory) -> Branch:
    """Return a committed branch the customers are registered at."""
    built = factory.branch(code="CBD")
    session.commit()
    return built


@pytest.fixture
def staff(session: Session, factory: Factory, branch: Branch) -> dict[str, str]:
    """Return the request headers of a counter assistant of the branch."""
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
    session.commit()
    return authorization_header(mint_access_token(assistant.id, role=assistant.role))


def a_customer(
    factory: Factory,
    branch: Branch,
    name: str,
    phone: str,
    *,
    email: str | None = None,
) -> CustomerProfile:
    """Return a customer with a name and a phone, and an account when an email is given."""
    account: UserAccount | None = None
    if email is not None:
        account = factory.user(role=UserRole.CUSTOMER, email=email)
    profile = factory.customer_profile(branch=branch, account=account)
    profile.display_name = name
    profile.contact_phone = phone
    factory.session.add(profile)
    factory.session.flush()
    return profile


def names_in(body: dict[str, object]) -> list[str]:
    """Return the display names on a page, in the order they were returned."""
    items = body["items"]
    assert isinstance(items, list)
    return [str(item["displayName"]) for item in items]


def search(client: TestClient, headers: dict[str, str], **params: object) -> dict[str, object]:
    """Search the customers and return the page, failing on anything but a 200."""
    response = client.get(CUSTOMERS_PATH, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    body: dict[str, object] = response.json()
    return body


@pytest.fixture
def customers(session: Session, factory: Factory, branch: Branch) -> list[CustomerProfile]:
    """Return four committed customers whose names and numbers a search can tell apart."""
    built = [
        a_customer(factory, branch, "Thandi Mokoena", "082 441 7719", email=THANDI_EMAIL),
        a_customer(factory, branch, "Sipho Thandeka", "(021) 555-0142"),
        a_customer(factory, branch, "Lerato Nkosi", "+27 73 228 5104"),
        a_customer(factory, branch, "Anna Thandiwe", "083 000 1111"),
    ]
    session.commit()
    return built


class TestTheCustomerSummary:
    """What the counter is told about a customer."""

    def test_a_customer_with_an_account_has_the_shape_of_the_contract(
        self,
        client: TestClient,
        staff: dict[str, str],
        branch: Branch,
        customers: list[CustomerProfile],
    ) -> None:
        (thandi,) = search(client, staff, q="Mokoena")["items"]
        assert thandi.keys() == SUMMARY_MEMBERS
        assert thandi == {
            "id": str(customers[0].id),
            "displayName": "Thandi Mokoena",
            "email": THANDI_EMAIL,
            "phone": "082 441 7719",
            "hasLogin": True,
            "emailVerified": False,
            "customerType": "INDIVIDUAL",
            "companyName": None,
            "idDocumentType": "SA_ID",
            "idDocumentLast4": customers[0].id_document_last4,
            "billingSuburb": customers[0].billing_suburb,
            "billingCity": customers[0].billing_city,
            "accountStatus": "ACTIVE",
            "tradeDiscountPercent": "0.00",
            "noShowCount": 0,
            "homeBranchCode": branch.code,
        }

    def test_a_walk_in_has_no_login_and_no_email(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        (lerato,) = search(client, staff, q="Lerato")["items"]
        assert (lerato["hasLogin"], lerato["email"], lerato["emailVerified"]) == (
            False, None, False
        )

    def test_one_customer_is_read_by_its_key(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        response = client.get(customer_path(customers[1].id), headers=staff)
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == search(client, staff, q="Sipho")["items"][0]

    def test_a_customer_nobody_registered_is_a_404_in_a_plain_sentence(
        self, client: TestClient, staff: dict[str, str]
    ) -> None:
        response = client.get(customer_path(uuid4()), headers=staff)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_of(response)["detail"] == (
            "We could not find that customer. Search for them again."
        )

    def test_a_key_that_is_not_a_key_is_refused_by_name(
        self, client: TestClient, staff: dict[str, str]
    ) -> None:
        response = client.get(customer_path("Thandi"), headers=staff)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == VALIDATION_PROBLEM

    def test_a_trade_customer_shows_the_company(
        self, client: TestClient, session: Session, factory: Factory, branch: Branch,
        staff: dict[str, str],
    ) -> None:
        trade = a_customer(factory, branch, "Bongani Builders", "021 448 9000")
        trade.customer_type = CustomerType.TRADE
        trade.company_name = "Bongani Builders (Pty) Ltd"
        session.add(trade)
        session.commit()
        (found,) = search(client, staff, q="Bongani")["items"]
        assert (found["customerType"], found["companyName"]) == (
            "TRADE", "Bongani Builders (Pty) Ltd"
        )


class TestMatching:
    """By name, by phone and by email, and never by a wildcard."""

    def test_part_of_a_name_matches_anywhere_and_ignores_case(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        assert sorted(names_in(search(client, staff, q="thand"))) == [
            "Anna Thandiwe", "Sipho Thandeka", "Thandi Mokoena"
        ]

    @pytest.mark.parametrize("typed", ["0824417719", "082 441 7719", "082-441-7719", "4417719"])
    def test_a_phone_number_matches_however_either_side_punctuated_it(
        self,
        client: TestClient,
        staff: dict[str, str],
        customers: list[CustomerProfile],
        typed: str,
    ) -> None:
        assert names_in(search(client, staff, q=typed)) == ["Thandi Mokoena"]

    def test_a_number_stored_with_brackets_and_a_plus_is_found_by_its_digits(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        assert names_in(search(client, staff, q="0215550142")) == ["Sipho Thandeka"]
        assert names_in(search(client, staff, q="27732285104")) == ["Lerato Nkosi"]

    def test_the_email_of_an_account_matches_exactly_and_ignores_case(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        assert names_in(search(client, staff, q=THANDI_EMAIL.upper())) == ["Thandi Mokoena"]
        assert search(client, staff, q="thandi.mokoena@example")["total"] == 0

    def test_two_digits_are_too_few_to_search_a_phone_by(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        assert search(client, staff, q="08")["total"] == 0

    @pytest.mark.parametrize("wildcard", ["%%", "__", "%_"])
    def test_a_wildcard_matches_nobody(
        self,
        client: TestClient,
        staff: dict[str, str],
        customers: list[CustomerProfile],
        wildcard: str,
    ) -> None:
        body = search(client, staff, q=wildcard)
        assert (body["items"], body["total"]) == ([], 0)


class TestTheOrder:
    """The best match first, and the same order on every call."""

    def test_an_exact_number_comes_before_a_name_that_starts_with_it(
        self, client: TestClient, session: Session, factory: Factory, branch: Branch,
        staff: dict[str, str],
    ) -> None:
        a_customer(factory, branch, "Zola 0821", "0821 999 999")
        a_customer(factory, branch, "Yusuf Dlamini", "0821")
        session.commit()
        assert names_in(search(client, staff, q="0821")) == ["Yusuf Dlamini", "Zola 0821"]

    def test_a_name_that_starts_with_the_text_then_a_word_that_does_then_any_other(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        assert names_in(search(client, staff, q="Thand")) == [
            "Thandi Mokoena", "Anna Thandiwe", "Sipho Thandeka"
        ]
        assert names_in(search(client, staff, q="and")) == [
            "Anna Thandiwe", "Sipho Thandeka", "Thandi Mokoena"
        ]


class TestPaging:
    """A page at a time, with the total across every page."""

    def test_a_page_has_the_shape_of_the_contract(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        body = search(client, staff, q="Thand")
        assert body.keys() == PAGE_MEMBERS
        assert (body["page"], body["pageSize"], body["total"]) == (1, 20, 3)

    def test_the_second_page_carries_on_where_the_first_stopped(
        self, client: TestClient, staff: dict[str, str], customers: list[CustomerProfile]
    ) -> None:
        first = search(client, staff, q="Thand", page=1, pageSize=2)
        second = search(client, staff, q="Thand", page=2, pageSize=2)
        assert names_in(first) + names_in(second) == names_in(search(client, staff, q="Thand"))
        assert (second["page"], second["pageSize"], second["total"]) == (2, 2, 3)

    @pytest.mark.parametrize(
        ("params", "field", "sentence"),
        [
            ({}, "query.q", "This is needed. Please fill it in."),
            ({"q": "T"}, "query.q", "Enter at least 2 characters."),
            ({"q": "  T  "}, "query.q", "Enter at least 2 characters."),
            ({"q": "x" * 81}, "query.q", "Enter at most 80 characters."),
            ({"q": "Thandi", "page": 0}, "query.page", "Enter 1 or more."),
            ({"q": "Thandi", "pageSize": 51}, "query.pageSize", "Enter 50 or less."),
        ],
    )
    def test_a_refused_parameter_is_named_in_a_plain_sentence(
        self,
        client: TestClient,
        staff: dict[str, str],
        params: dict[str, object],
        field: str,
        sentence: str,
    ) -> None:
        response = client.get(CUSTOMERS_PATH, params=params, headers=staff)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == VALIDATION_PROBLEM
        assert problem_of(response)["errors"] == {"fields": {field: sentence}}
