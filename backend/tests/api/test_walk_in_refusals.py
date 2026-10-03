"""Every field of a walk-in is checked, through HTTP (US-20).

A value a rule refuses is named with a plain sentence. A value the framework
refuses for its type, its length or its pattern is named in the framework's
own words, as every request body is, and so is a field the contract does not
have, so a submitted `accountStatus` or `tradeDiscountPercent` never reaches
the database. Nothing is stored for a refused walk-in.

The answer to a walk-in that is accepted, and the branch rules, are pinned in
tests/api/test_walk_in.py. These run against the in memory database.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.enums import CustomerType, UserRole
from app.infrastructure.models import CustomerProfile, UserAccount
from tests.support.checkout_api import CUSTOMERS_PATH
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.walk_in_api import headers_of, walk_in_body

VALIDATION_PROBLEM: Final[str] = "request-validation-failure"
TRADE_NEEDS_A_COMPANY: Final[str] = "A trade account needs its company name."
PHONE_SENTENCE: Final[str] = (
    "Enter a phone number of at least seven digits. Spaces, brackets and hyphens are fine."
)


@pytest.fixture
def assistant(session: Session, factory: Factory) -> UserAccount:
    """Return a committed counter assistant of a branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch(code="CBD"))
    session.commit()
    return account


@pytest.mark.parametrize(
    ("changes", "field", "sentence"),
    [
        ({"customerType": "TRADE"}, "body.companyName", TRADE_NEEDS_A_COMPANY),
        (
            {"customerType": "TRADE", "companyName": "   "},
            "body.companyName",
            TRADE_NEEDS_A_COMPANY,
        ),
        ({"phone": "call me later"}, "body.phone", PHONE_SENTENCE),
    ],
)
def test_a_rule_names_the_field_in_a_plain_sentence(
    client: TestClient,
    session: Session,
    assistant: UserAccount,
    changes: dict[str, object],
    field: str,
    sentence: str,
) -> None:
    response = client.post(
        CUSTOMERS_PATH, json=walk_in_body(**changes), headers=headers_of(assistant)
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_of(response)["errors"] == {"fields": {field: sentence}}
    assert session.exec(select(CustomerProfile)).all() == []


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"displayName": None}, "body.displayName"),
        ({"displayName": "   "}, "body.displayName"),
        ({"displayName": "x" * 121}, "body.displayName"),
        ({"phone": ""}, "body.phone"),
        ({"idDocumentType": "BIRTH_CERTIFICATE"}, "body.idDocumentType"),
        ({"idDocumentLast4": "12"}, "body.idDocumentLast4"),
        ({"idDocumentLast4": "12-4"}, "body.idDocumentLast4"),
        ({"billingPostalCode": "x" * 11}, "body.billingPostalCode"),
        ({"customerType": "WHOLESALE"}, "body.customerType"),
        ({"branchCode": "TOOLONG"}, "body.branchCode"),
        ({"accountStatus": "ACTIVE"}, "body.accountStatus"),
        ({"tradeDiscountPercent": "25.00"}, "body.tradeDiscountPercent"),
    ],
)
def test_a_value_the_framework_refuses_names_the_field(
    client: TestClient,
    session: Session,
    assistant: UserAccount,
    changes: dict[str, object],
    field: str,
) -> None:
    response = client.post(
        CUSTOMERS_PATH, json=walk_in_body(**changes), headers=headers_of(assistant)
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_code(response) == VALIDATION_PROBLEM
    fields = problem_of(response)["errors"]
    assert isinstance(fields, dict)
    assert set(fields["fields"]) == {field}
    assert session.exec(select(CustomerProfile)).all() == []


def test_an_individual_may_still_carry_a_company_and_a_blank_one_is_dropped(
    client: TestClient, assistant: UserAccount
) -> None:
    response = client.post(
        CUSTOMERS_PATH,
        json=walk_in_body(companyName="  ", vatNumber=" "),
        headers=headers_of(assistant),
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert (body["customerType"], body["companyName"]) == (CustomerType.INDIVIDUAL.value, None)
