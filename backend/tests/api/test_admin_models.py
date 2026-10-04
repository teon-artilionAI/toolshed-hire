"""The product models of the admin catalogue, through HTTP (FR-22, US-30, BR-20, BR-49).

The administrator lists the models, published or not, with how many units the
fleet holds of each, narrows the list by text, category and publication, and
reads one. A new model answers 201 and starts unpublished. An edit of a rate
answers 200 and records the rate before and after. Publishing puts a model in
the public catalogue and hiding it takes it out at once. These run against the
in memory database on the still clock of the booking tests. The refusals are in
tests/api/test_admin_model_refusals.py.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, Branch, Category, UserAccount
from tests.support.admin_api import PAGE_MEMBERS
from tests.support.admin_catalogue_api import (
    DAILY_AFTER,
    MODEL_MEMBERS,
    create_model,
    edit_model,
    list_models,
    model_body,
    publish,
    read_model,
)
from tests.support.booking_api import BookingClient, answered, created
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory
from tests.support.http import problem_code

UPDATED_AT: str = "2026-03-02T10:00:00+02:00"


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


@pytest.fixture
def branch(session: Session, factory: Factory) -> Branch:
    """Return a committed branch."""
    row = factory.branch()
    session.commit()
    return row


def event_actions(session: Session, entity_id: object) -> list[AuditEvent]:
    """Return the audit events about one record, oldest first."""
    statement = (
        select(AuditEvent)
        .where(col(AuditEvent.entity_id) == UUID(str(entity_id)))
        .order_by(col(AuditEvent.id))
    )
    return list(session.exec(statement).all())


class TestTheList:
    """Every model, published or not, by name, with its units, narrowed as asked."""

    def test_published_and_hidden_models_are_listed_by_name_with_their_units(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        category: Category,
        branch: Branch,
    ) -> None:
        hammer = a_model(factory, name="Rotary hammer", category=category)
        breaker = a_model(factory, name="Breaker", category=category, is_published=False)
        for _ in range(2):
            factory.asset(product_model=hammer, branch=branch)
        session.commit()
        page = answered(list_models(booking, administrator))
        assert set(page) == PAGE_MEMBERS
        assert [item["name"] for item in page["items"]] == ["Breaker", "Rotary hammer"]
        first, second = page["items"]
        assert set(first) == MODEL_MEMBERS
        assert (first["id"], first["isPublished"], first["assetCount"]) == (
            str(breaker.id),
            False,
            0,
        )
        assert (second["assetCount"], second["categoryName"], second["dailyRate"]) == (
            2,
            "Drilling",
            "185.00",
        )

    def test_the_list_is_narrowed_by_text_category_and_publication(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        category: Category,
    ) -> None:
        other = a_category(factory, name="Gardening")
        a_model(factory, name="Rotary hammer", category=category)
        a_model(factory, name="Breaker", category=category, is_published=False)
        a_model(factory, name="Hedge trimmer", category=other, manufacturer="Stihl")
        session.commit()

        def names(**params: object) -> list[str]:
            page = answered(list_models(booking, administrator, **params))
            return [item["name"] for item in page["items"]]

        assert names(categoryId=str(category.id)) == ["Breaker", "Rotary hammer"]
        assert names(published="false") == ["Breaker"]
        assert names(categoryId=str(category.id), published="true") == ["Rotary hammer"]
        assert names(q="stihl") == ["Hedge trimmer"]

    def test_a_page_is_cut_from_the_list(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        category: Category,
    ) -> None:
        for name in ("A", "B", "C"):
            a_model(factory, name=f"{name} hammer", category=category)
        session.commit()
        page = answered(list_models(booking, administrator, page=2, pageSize=2))
        assert ([item["name"] for item in page["items"]], page["total"]) == (["C hammer"], 3)

    def test_one_model_is_read_published_or_not(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        category: Category,
    ) -> None:
        hidden = a_model(factory, name="Breaker", category=category, is_published=False)
        session.commit()
        body = answered(read_model(booking, administrator, hidden.id))
        assert (body["id"], body["isPublished"]) == (str(hidden.id), False)

    def test_a_model_nobody_can_find_is_not_found(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = read_model(booking, administrator, "00000000-0000-4000-8000-000000000000")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == "not-found"


class TestCreatingAndEditingAModel:
    """A new model starts unpublished, and a rate change records the rate before and after."""

    def test_a_model_is_created_unpublished_and_recorded(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        category: Category,
    ) -> None:
        body = created(create_model(booking, administrator, model_body(category.id)))
        assert set(body) == MODEL_MEMBERS
        assert (body["isPublished"], body["dailyRate"], body["assetCount"], body["updatedAt"]) == (
            False,
            "280.00",
            0,
            UPDATED_AT,
        )
        (event,) = event_actions(session, body["id"])
        assert event.action == "product_model.created"

    def test_a_model_created_hidden_on_purpose_is_accepted(
        self, booking: BookingClient, administrator: UserAccount, category: Category
    ) -> None:
        body = created(
            create_model(booking, administrator, model_body(category.id, isPublished=False))
        )
        assert body["isPublished"] is False

    def test_a_rate_change_is_answered_and_recorded_before_and_after(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        category: Category,
    ) -> None:
        model = created(create_model(booking, administrator, model_body(category.id)))
        body = answered(edit_model(booking, administrator, model["id"], {"dailyRate": DAILY_AFTER}))
        assert (body["dailyRate"], body["sku"]) == (DAILY_AFTER, "DR-BOSCH-GBH226")
        _, edited = event_actions(session, model["id"])
        assert (edited.action, edited.before_state, edited.after_state) == (
            "product_model.updated",
            {"daily_rate": "280.00"},
            {"daily_rate": "310.00"},
        )

    def test_a_long_description_is_written_and_then_cleared_with_null(
        self, booking: BookingClient, administrator: UserAccount, category: Category
    ) -> None:
        model = created(create_model(booking, administrator, model_body(category.id)))
        written = answered(
            edit_model(booking, administrator, model["id"], {"longDescription": "Strong."})
        )
        cleared = answered(
            edit_model(booking, administrator, model["id"], {"longDescription": None})
        )
        assert (written["longDescription"], cleared["longDescription"]) == ("Strong.", None)


class TestPublishing:
    """Publishing puts a model in the public catalogue, and hiding it takes it out at once."""

    def test_a_published_model_reaches_the_public_catalogue_and_leaves_it_when_hidden(
        self, booking: BookingClient, administrator: UserAccount, category: Category
    ) -> None:
        model = created(create_model(booking, administrator, model_body(category.id)))
        public_path = f"/api/catalogue/models/{model['slug']}"
        assert booking.client.get(public_path).status_code == status.HTTP_404_NOT_FOUND
        assert answered(publish(booking, administrator, model["id"], True))["isPublished"] is True
        assert booking.client.get(public_path).status_code == status.HTTP_200_OK
        assert answered(publish(booking, administrator, model["id"], False))["isPublished"] is False
        assert booking.client.get(public_path).status_code == status.HTTP_404_NOT_FOUND
        listed = answered(booking.client.get("/api/catalogue/models"))
        assert listed["total"] == 0

    def test_each_change_of_publication_writes_its_own_event(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        category: Category,
    ) -> None:
        model = created(create_model(booking, administrator, model_body(category.id)))
        answered(publish(booking, administrator, model["id"], True))
        answered(publish(booking, administrator, model["id"], True))
        answered(publish(booking, administrator, model["id"], False))
        assert [event.action for event in event_actions(session, model["id"])] == [
            "product_model.created",
            "product_model.published",
            "product_model.unpublished",
        ]

    def test_a_model_nobody_can_find_cannot_be_published(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = publish(booking, administrator, "00000000-0000-4000-8000-000000000000", True)
        assert response.status_code == status.HTTP_404_NOT_FOUND
