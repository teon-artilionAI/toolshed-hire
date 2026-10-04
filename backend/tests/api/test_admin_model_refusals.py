"""Every refusal of the product model routes, through HTTP (FR-22, BR-21, BR-22, BR-44).

Each rule of the contract is a 422 naming its field. A duplicate SKU or slug,
money below zero, a weekly rate above seven days at the daily rate, a
shortest hire longer than the longest and a category that is switched off.
An edit that sends the SKU is refused naming it, because a SKU never changes,
a new model cannot ask to be published, and a field that may not be empty
cannot be sent as null. A refused write keeps nothing. Every route answers 403
to counter staff and customers. These run against the in memory database.
"""

from __future__ import annotations

import pytest
from fastapi import status
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import Category, ProductModel, UserAccount
from tests.support.admin_catalogue_api import (
    create_model,
    edit_model,
    list_models,
    model_body,
    publish,
    read_model,
)
from tests.support.booking_api import BookingClient, created
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory
from tests.support.report_api import refused_fields


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def category(session: Session, factory: Factory) -> Category:
    """Return a committed active category."""
    row = a_category(factory, name="Drilling")
    session.commit()
    return row


def stored_skus(session: Session) -> list[str]:
    """Return the SKUs of every stored model."""
    return list(session.exec(select(ProductModel.sku)).all())


class TestCreatingRefusesEachRule:
    """A creation that breaks a rule is a 422 naming the field, and keeps nothing."""

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"dailyRate": "-1.00"}, "body.dailyRate"),
            ({"depositAmount": "-0.01"}, "body.depositAmount"),
            ({"lateFeePerDay": "-5"}, "body.lateFeePerDay"),
            ({"replacementValue": "-100.00"}, "body.replacementValue"),
            ({"weeklyRate": "1960.01"}, "body.weeklyRate"),
            ({"minHireDays": 8, "maxHireDays": 7}, "body.minHireDays"),
            ({"maxHireDays": 29}, "body.maxHireDays"),
            ({"sku": "dr-bosch"}, "body.sku"),
            ({"slug": "Bosch Hammer"}, "body.slug"),
            ({"dailyRate": 280}, "body.dailyRate"),
            ({"dailyRate": "280.005"}, "body.dailyRate"),
            ({"isPublished": True}, "body.isPublished"),
            ({"imagePath": "hammer.jpg"}, "body.imagePath"),
        ],
    )
    def test_a_member_that_breaks_a_rule_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        category: Category,
        members: dict[str, object],
        field: str,
    ) -> None:
        response = create_model(booking, administrator, model_body(category.id, **members))
        assert refused_fields(response) == {field}
        assert stored_skus(session) == []

    def test_a_category_that_was_switched_off_is_refused_naming_it(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        off = a_category(factory, name="Old stock", is_active=False)
        session.commit()
        response = create_model(booking, administrator, model_body(off.id))
        assert refused_fields(response) == {"body.categoryId"}

    def test_a_category_nobody_can_find_is_refused_naming_it(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        body = model_body("00000000-0000-4000-8000-000000000000")
        assert refused_fields(create_model(booking, administrator, body)) == {"body.categoryId"}

    @pytest.mark.parametrize(("member", "field"), [("sku", "body.sku"), ("slug", "body.slug")])
    def test_a_sku_or_slug_another_model_holds_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        category: Category,
        member: str,
        field: str,
    ) -> None:
        held = a_model(factory, name="Hammer", category=category)
        session.commit()
        value = held.sku if member == "sku" else held.slug
        response = create_model(booking, administrator, model_body(category.id, **{member: value}))
        assert refused_fields(response) == {field}


class TestEditingRefusesEachRule:
    """An edit that breaks a rule is a 422 naming the field, and changes nothing."""

    @pytest.fixture
    def model_id(
        self, booking: BookingClient, administrator: UserAccount, category: Category
    ) -> object:
        """Return the key of a model created through the route."""
        return created(create_model(booking, administrator, model_body(category.id)))["id"]

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"sku": "DR-OTHER"}, "body.sku"),
            ({"weeklyRate": "5000.00"}, "body.weeklyRate"),
            ({"dailyRate": "100.00"}, "body.weeklyRate"),
            ({"minHireDays": 20, "maxHireDays": 10}, "body.minHireDays"),
            ({"name": None}, "body.name"),
            ({"dailyRate": None}, "body.dailyRate"),
            ({"isPublished": None}, "body.isPublished"),
            ({"replacementValue": "-1.00"}, "body.replacementValue"),
        ],
    )
    def test_a_member_that_breaks_a_rule_is_refused_naming_it(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        model_id: object,
        members: dict[str, object],
        field: str,
    ) -> None:
        response = edit_model(booking, administrator, model_id, members)
        assert refused_fields(response) == {field}
        stored = read_model(booking, administrator, model_id).json()
        assert (stored["dailyRate"], stored["weeklyRate"]) == ("280.00", "1120.00")

    def test_a_slug_another_model_holds_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        category: Category,
        model_id: object,
    ) -> None:
        held = a_model(factory, name="Breaker", category=category)
        session.commit()
        response = edit_model(booking, administrator, model_id, {"slug": held.slug})
        assert refused_fields(response) == {"body.slug"}

    def test_a_move_to_a_category_that_was_switched_off_is_refused(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        model_id: object,
    ) -> None:
        off = a_category(factory, name="Old stock", is_active=False)
        session.commit()
        response = edit_model(booking, administrator, model_id, {"categoryId": str(off.id)})
        assert refused_fields(response) == {"body.categoryId"}

    def test_a_model_nobody_can_find_is_not_found(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = edit_model(
            booking, administrator, "00000000-0000-4000-8000-000000000000", {"name": "Hammer"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_a_publication_that_is_not_a_yes_or_a_no_is_refused(
        self, booking: BookingClient, administrator: UserAccount, model_id: object
    ) -> None:
        response = publish(booking, administrator, model_id, None)
        assert refused_fields(response) == {"body.published"}


class TestWhoMayCall:
    """Only an administrator. Counter staff and customers are refused with 403."""

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_staff_and_customers_are_refused_every_route(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        category: Category,
        role: UserRole,
    ) -> None:
        branch = factory.branch() if role is UserRole.COUNTER_STAFF else None
        account = factory.user(role=role, branch=branch)
        model = a_model(factory, name="Hammer", category=category)
        session.commit()
        responses = [
            list_models(booking, account),
            read_model(booking, account, model.id),
            create_model(booking, account, model_body(category.id)),
            edit_model(booking, account, model.id, {"dailyRate": "310.00"}),
            publish(booking, account, model.id, False),
        ]
        assert [response.status_code for response in responses] == [
            status.HTTP_403_FORBIDDEN
        ] * 5
