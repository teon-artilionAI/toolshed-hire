"""`GET /api/me/profile` and `PATCH /api/me/profile`, through HTTP and real SQL (US-05, C-26).

A customer reads their own details and changes eight of them. The profile is
found by the account that is signed in, so a staff account and an account
with no profile have nothing to read. The name and the phone number live on
the account and on the profile, and an edit writes both copies.

Any field outside the eight is refused by name with a 422, and the refusal
leaves both rows exactly as they were, so a submitted account status, role or
discount never reaches the database. An edit that changes something writes one
audit event that names the fields and keeps none of their new values.

Most tests build the customer with the factories. One registers through the
API, to prove the profile reads back what a person registered with.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, Branch, CustomerProfile, UserAccount
from tests.support.accounts_api import (
    NEW_EMAIL,
    PROFILE_PATH,
    REGISTER_PATH,
    REQUEST_VALIDATION_PROBLEM,
    registration_body,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.tokens import authorization_header, mint_access_token

PROFILE_UPDATED_ACTION: Final[str] = "customer.profile_updated"
DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# One accepted new value for each of the eight fields a customer may change.
EDITS: Final[dict[str, str]] = {
    "fullName": "Thandi Mokoena-Dlamini",
    "phone": "021 555 0199",
    "billingAddressLine1": "3 Kloof Nek Road",
    "billingSuburb": "Tamboerskloof",
    "billingCity": "Stellenbosch",
    "billingPostalCode": "7600",
    "companyName": "Mokoena Plant Hire",
    "vatNumber": "4123456789",
}
# Fields a customer may not change, each with a value it might be tried with.
FORBIDDEN: Final[dict[str, str]] = {
    "accountStatus": "BLACKLISTED",
    "role": "ADMIN",
    "tradeDiscountPercent": "25.00",
    "email": "somebody.else@example.co.za",
    "idDocumentLast4": "9999",
}
OVERLONG_POSTAL_CODE: Final[str] = "12345678901"
ANY_EDIT: Final[dict[str, str]] = {"billingCity": "Paarl"}


def bearer(account: UserAccount, clock: FixedClock) -> dict[str, str]:
    """Return the header of an access token for an account, issued at the still clock."""
    token = mint_access_token(
        account.id, role=account.role, branch_id=account.branch_id, issued_at=clock.now()
    )
    return authorization_header(token)


@dataclass(frozen=True, slots=True)
class SignedInCustomer:
    """A customer with a profile, and the client and token they call the routes with."""

    client: TestClient
    account: UserAccount
    headers: dict[str, str]

    def read(self) -> Response:
        """Read the profile."""
        return self.client.get(PROFILE_PATH, headers=self.headers)

    def edit(self, body: object) -> Response:
        """Send one edit of the profile."""
        return self.client.patch(PROFILE_PATH, json=body, headers=self.headers)


@pytest.fixture
def me(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch: Branch,
    still_clock: FixedClock,
) -> SignedInCustomer:
    """Return a committed customer with a profile at the home branch, ready to call."""
    account = factory.user()
    factory.customer_profile(branch=home_branch, account=account)
    session.commit()
    return SignedInCustomer(account_api, account, bearer(account, still_clock))


def profile_row(session: Session, account: UserAccount) -> CustomerProfile:
    """Return the profile row of an account as the database now holds it."""
    session.expire_all()
    statement = select(CustomerProfile).where(col(CustomerProfile.user_account_id) == account.id)
    return session.exec(statement).one()


def both_rows(session: Session, account: UserAccount) -> tuple[dict[str, object], ...]:
    """Return every column of the account row and of its profile row."""
    profile = profile_row(session, account)
    session.refresh(account)
    return account.model_dump(), profile.model_dump()


def profile_events(session: Session) -> list[AuditEvent]:
    """Return the audit events of profile edits, oldest first."""
    statement = (
        select(AuditEvent)
        .where(col(AuditEvent.action) == PROFILE_UPDATED_ACTION)
        .order_by(col(AuditEvent.id))
    )
    return list(session.exec(statement).all())


def refused_fields(response: Response) -> dict[str, object]:
    """Return the fields a 422 names, after checking it is the refusal of a request."""
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_code(response) == REQUEST_VALIDATION_PROBLEM
    errors = problem_of(response)["errors"]
    assert isinstance(errors, dict)
    fields = errors["fields"]
    assert isinstance(fields, dict)
    return fields


class TestReadingTheProfile:
    """The caller's own details, every field of the contract and no other."""

    def test_a_registered_customer_reads_back_what_they_registered_with(
        self,
        account_api: TestClient,
        session: Session,
        still_clock: FixedClock,
        home_branch: Branch,
    ) -> None:
        registered = account_api.post(REGISTER_PATH, json=registration_body())
        assert registered.status_code == status.HTTP_202_ACCEPTED
        account = session.exec(select(UserAccount).where(col(UserAccount.email) == NEW_EMAIL)).one()
        response = account_api.get(PROFILE_PATH, headers=bearer(account, still_clock))
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert DATE_PATTERN.match(body.pop("memberSince"))
        assert body == {
            "fullName": "Thandi Mokoena",
            "email": NEW_EMAIL,
            "emailVerified": False,
            "phone": "0824417719",
            "customerType": "INDIVIDUAL",
            "companyName": None,
            "vatNumber": None,
            "idDocumentType": "SA_ID",
            "idDocumentLast4": "5083",
            "billingAddressLine1": "12 Loop Street",
            "billingSuburb": "Gardens",
            "billingCity": "Cape Town",
            "billingPostalCode": "8001",
            "accountStatus": "ACTIVE",
            "tradeDiscountPercent": "0.00",
            "noShowCount": 0,
            "homeBranchCode": home_branch.code,
        }

    def test_a_customer_account_with_no_profile_is_404(
        self, account_api: TestClient, session: Session, factory: Factory, still_clock: FixedClock
    ) -> None:
        account = factory.user()
        session.commit()
        caller = SignedInCustomer(account_api, account, bearer(account, still_clock))
        assert caller.read().status_code == status.HTTP_404_NOT_FOUND
        assert caller.edit(ANY_EDIT).status_code == status.HTTP_404_NOT_FOUND

    def test_counter_staff_and_an_administrator_are_403(
        self,
        account_api: TestClient,
        session: Session,
        factory: Factory,
        still_clock: FixedClock,
        home_branch: Branch,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=home_branch)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        for account in (assistant, administrator):
            caller = SignedInCustomer(account_api, account, bearer(account, still_clock))
            assert caller.read().status_code == status.HTTP_403_FORBIDDEN
            assert caller.edit(ANY_EDIT).status_code == status.HTTP_403_FORBIDDEN

    def test_a_request_with_no_credential_is_401(self, account_api: TestClient) -> None:
        assert account_api.get(PROFILE_PATH).status_code == status.HTTP_401_UNAUTHORIZED
        unsigned_edit = account_api.patch(PROFILE_PATH, json=ANY_EDIT)
        assert unsigned_edit.status_code == status.HTTP_401_UNAUTHORIZED


class TestEditingTheProfile:
    """The eight fields change, and everything else is refused by name."""

    @pytest.mark.parametrize(("field", "value"), list(EDITS.items()))
    def test_each_editable_field_changes_and_the_profile_is_returned(
        self, me: SignedInCustomer, field: str, value: str
    ) -> None:
        before = me.read().json()
        response = me.edit({field: value})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {**before, field: value}
        assert me.read().json() == response.json()

    def test_a_new_full_name_is_written_to_the_account_and_to_the_profile(
        self, me: SignedInCustomer, session: Session
    ) -> None:
        me.edit({"fullName": EDITS["fullName"]})
        assert profile_row(session, me.account).display_name == EDITS["fullName"]
        session.refresh(me.account)
        assert me.account.full_name == EDITS["fullName"]

    def test_a_new_phone_is_written_to_the_account_and_to_the_profile(
        self, me: SignedInCustomer, session: Session
    ) -> None:
        me.edit({"phone": EDITS["phone"]})
        assert profile_row(session, me.account).contact_phone == EDITS["phone"]
        session.refresh(me.account)
        assert me.account.phone == EDITS["phone"]

    def test_the_company_name_and_the_vat_number_are_cleared_with_null(
        self, me: SignedInCustomer, session: Session
    ) -> None:
        trade_details = {"companyName": EDITS["companyName"], "vatNumber": EDITS["vatNumber"]}
        assert me.edit(trade_details).status_code == status.HTTP_200_OK
        cleared = me.edit({"companyName": None, "vatNumber": None})
        assert cleared.status_code == status.HTTP_200_OK
        assert cleared.json()["companyName"] is None
        assert cleared.json()["vatNumber"] is None
        row = profile_row(session, me.account)
        assert row.company_name is None
        assert row.vat_number is None

    @pytest.mark.parametrize(("field", "value"), list(FORBIDDEN.items()))
    def test_a_field_the_customer_may_not_change_is_422_and_changes_nothing(
        self, me: SignedInCustomer, session: Session, field: str, value: str
    ) -> None:
        before = both_rows(session, me.account)
        response = me.edit({"fullName": EDITS["fullName"], field: value})
        assert f"body.{field}" in refused_fields(response)
        assert both_rows(session, me.account) == before
        assert profile_events(session) == []

    @pytest.mark.parametrize(
        ("field", "value"), [("fullName", "   "), ("billingPostalCode", OVERLONG_POSTAL_CODE)]
    )
    def test_a_blank_name_or_an_overlong_postal_code_is_422_naming_the_field(
        self, me: SignedInCustomer, session: Session, field: str, value: str
    ) -> None:
        before = both_rows(session, me.account)
        assert f"body.{field}" in refused_fields(me.edit({field: value}))
        assert both_rows(session, me.account) == before


class TestTheAuditTrail:
    """One event for an edit that changes something, naming the fields and not the values."""

    def test_a_change_writes_one_event_that_names_the_fields_and_holds_no_value(
        self, me: SignedInCustomer, session: Session
    ) -> None:
        changes = {"phone": EDITS["phone"], "billingCity": EDITS["billingCity"]}
        assert me.edit(changes).status_code == status.HTTP_200_OK
        (event,) = profile_events(session)
        assert event.after_state is not None
        assert set(event.after_state["changed_fields"]) == {"phone", "billing_city"}
        recorded = json.dumps([event.before_state, event.after_state])
        assert all(value not in recorded for value in changes.values())
        assert event.entity_id == profile_row(session, me.account).id
        assert event.actor_user_id == me.account.id

    def test_an_edit_that_changes_nothing_writes_no_event(
        self, me: SignedInCustomer, session: Session
    ) -> None:
        current_city = profile_row(session, me.account).billing_city
        assert me.edit({}).status_code == status.HTTP_200_OK
        assert me.edit({"billingCity": current_city}).status_code == status.HTTP_200_OK
        assert profile_events(session) == []
