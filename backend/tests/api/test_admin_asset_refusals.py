"""Every refusal of the asset register routes but a move's, through HTTP (FR-23, BR-34).

A registration that breaks a rule, names a model or a branch nobody can
find, or repeats a tag another unit carries is a 422 naming the field. An
edit that sends the tag, the model or the branch is refused naming it,
because none of them ever changes (BR-34). A refused write keeps nothing. A
tag nobody carries is a 404, a list parameter out of bounds is a 422 naming
it, and every route answers 403 to counter staff and customers. These run
against the in memory database. The refusals of a move are in
tests/api/test_admin_asset_move_refusals.py.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import (
    Asset,
    Branch,
    ProductModel,
    UserAccount,
)
from tests.support.admin_asset_api import (
    NEW_TAG,
    asset_body,
    create_asset,
    edit_asset,
    list_assets,
    move_asset,
    read_asset,
    stored_events,
    stored_tags,
)
from tests.support.booking_api import BookingClient
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.report_api import refused_fields

TAG: Final[str] = "TSH-DR-0042"
UNKNOWN_TAG: Final[str] = "TSH-ZZ-0000"
UNKNOWN_KEY: Final[str] = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def branch(session: Session, factory: Factory) -> Branch:
    """Return the committed CBD branch."""
    row = factory.branch(code="CBD")
    session.commit()
    return row


@pytest.fixture
def model(session: Session, factory: Factory) -> ProductModel:
    """Return a committed model in an active category."""
    row = a_model(factory, name="Rotary hammer", category=a_category(factory, name="Drilling"))
    session.commit()
    return row


@pytest.fixture
def unit(session: Session, factory: Factory, branch: Branch, model: ProductModel) -> Asset:
    """Return a committed unit on the shelf at CBD."""
    row = factory.asset(product_model=model, branch=branch, asset_tag=TAG)
    session.commit()
    return row


class TestRegisteringRefusesEachRule:
    """A registration that breaks a rule is a 422 naming the field, and keeps nothing."""

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"assetTag": "tsh-dr-0099"}, "body.assetTag"),
            ({"assetTag": "TSH DR 0099"}, "body.assetTag"),
            ({"assetTag": "TSH-DRILL-0000099"}, "body.assetTag"),
            ({"assetTag": TAG}, "body.assetTag"),
            ({"modelId": UNKNOWN_KEY}, "body.modelId"),
            ({"modelId": "hammer"}, "body.modelId"),
            ({"branchCode": "XYZ"}, "body.branchCode"),
            ({"acquiredOn": "2026-03-03"}, "body.acquiredOn"),
            ({"acquisitionCost": "-1.00"}, "body.acquisitionCost"),
            ({"acquisitionCost": "10.005"}, "body.acquisitionCost"),
            ({"acquisitionCost": 3900}, "body.acquisitionCost"),
            ({"hourMeterReading": -1}, "body.hourMeterReading"),
            ({"conditionGrade": "D"}, "body.conditionGrade"),
            ({"serialNumber": "S" * 61}, "body.serialNumber"),
            ({"status": "AVAILABLE"}, "body.status"),
        ],
    )
    def test_a_member_that_breaks_a_rule_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        model: ProductModel,
        unit: Asset,
        members: dict[str, object],
        field: str,
    ) -> None:
        body = asset_body(model.id, "CBD", **members)
        assert refused_fields(create_asset(booking, administrator, body)) == {field}
        assert (stored_tags(session), stored_events(session)) == ([TAG], [])

    def test_a_branch_that_stopped_trading_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        model: ProductModel,
    ) -> None:
        closed = factory.branch(code="OLD")
        closed.is_active = False
        session.add(closed)
        session.commit()
        response = create_asset(booking, administrator, asset_body(model.id, "OLD"))
        assert refused_fields(response) == {"body.branchCode"}

    def test_a_registration_with_no_tag_is_refused_naming_it(
        self, booking: BookingClient, administrator: UserAccount, model: ProductModel
    ) -> None:
        body = asset_body(model.id, "CBD")
        del body["assetTag"]
        assert refused_fields(create_asset(booking, administrator, body)) == {"body.assetTag"}


class TestEditingRefusesWhatNeverChanges:
    """The tag, the model and the branch are refused by name, and so is a rule broken."""

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"assetTag": "TSH-DR-0100"}, "body.assetTag"),
            ({"modelId": UNKNOWN_KEY}, "body.modelId"),
            ({"branchCode": "BLV"}, "body.branchCode"),
            ({"status": "RETIRED"}, "body.status"),
            ({"conditionGrade": None}, "body.conditionGrade"),
            ({"hourMeterReading": -5}, "body.hourMeterReading"),
            ({"notes": "N" * 2001}, "body.notes"),
        ],
    )
    def test_a_member_that_may_not_be_sent_or_breaks_a_rule_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        unit: Asset,
        members: dict[str, object],
        field: str,
    ) -> None:
        assert refused_fields(edit_asset(booking, administrator, TAG, members)) == {field}
        assert stored_events(session) == []

    def test_a_tag_nobody_carries_is_not_found(
        self, booking: BookingClient, administrator: UserAccount, unit: Asset
    ) -> None:
        response = edit_asset(booking, administrator, UNKNOWN_TAG, {"notes": "x"})
        assert problem_code(response) == "not-found"
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestTheReadsRefuse:
    """A tag nobody carries is a 404, and a list parameter out of bounds is named."""

    def test_a_tag_nobody_carries_is_not_found(
        self, booking: BookingClient, administrator: UserAccount, unit: Asset
    ) -> None:
        response = read_asset(booking, administrator, UNKNOWN_TAG)
        assert (response.status_code, problem_code(response)) == (
            status.HTTP_404_NOT_FOUND,
            "not-found",
        )

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"q": "d"}, "query.q"),
            ({"q": "d" * 81}, "query.q"),
            ({"status": "BROKEN"}, "query.status"),
            ({"branchCode": "XYZ"}, "query.branchCode"),
            ({"modelId": "hammer"}, "query.modelId"),
            ({"page": 0}, "query.page"),
            ({"pageSize": 101}, "query.pageSize"),
        ],
    )
    def test_a_list_parameter_out_of_bounds_is_refused_naming_it(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        branch: Branch,
        params: dict[str, object],
        field: str,
    ) -> None:
        assert refused_fields(list_assets(booking, administrator, **params)) == {field}


class TestOnlyAnAdministrator:
    """Counter staff and customers are refused every route of the register."""

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_every_route_answers_403_to_anybody_but_an_administrator(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        branch: Branch,
        model: ProductModel,
        unit: Asset,
        role: UserRole,
    ) -> None:
        caller = factory.user(
            role=role, branch=branch if role is UserRole.COUNTER_STAFF else None
        )
        session.commit()
        answers = [
            list_assets(booking, caller),
            read_asset(booking, caller, TAG),
            create_asset(booking, caller, asset_body(model.id, "CBD")),
            edit_asset(booking, caller, TAG, {"notes": "x"}),
            move_asset(booking, caller, TAG, "QUARANTINED"),
        ]
        assert {response.status_code for response in answers} == {status.HTTP_403_FORBIDDEN}
        assert (stored_tags(session), stored_events(session)) == ([TAG], [])
        assert NEW_TAG not in stored_tags(session)
