"""The categories of the admin catalogue, through HTTP (FR-22, BR-44, BR-49, BR-51).

The administrator lists every category, switched off or not, each top level
category followed by its children, with the models each classifies itself.
Creating one answers 201 and switching one off answers 200, each with its
audit event. Nesting stops at two levels, a code or a slug another category
holds is refused naming it, and every route answers 403 to counter staff and
customers. These run against the in memory database on the still clock of the
booking tests.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import status
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, Category, UserAccount
from tests.support.admin_api import PAGE_MEMBERS
from tests.support.admin_catalogue_api import (
    CATEGORY_MEMBERS,
    category_body,
    create_category,
    edit_category,
    list_categories,
)
from tests.support.booking_api import BookingClient, answered, created
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.report_api import refused_fields


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


def events_of(session: Session, entity_id: object) -> list[AuditEvent]:
    """Return the audit events about one record, oldest first."""
    statement = (
        select(AuditEvent)
        .where(col(AuditEvent.entity_id) == UUID(str(entity_id)))
        .order_by(col(AuditEvent.id))
    )
    return list(session.exec(statement).all())


class TestTheList:
    """Every category, active or not, each parent followed by its children."""

    def test_parents_come_first_and_categories_switched_off_are_listed(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        garden = a_category(factory, name="Gardening", sort_order=30)
        access = a_category(factory, name="Access and lifting", sort_order=10)
        lifting = a_category(factory, name="Lifting", sort_order=1, parent=access)
        ladders = a_category(factory, name="Ladders", sort_order=2, parent=access)
        off = a_category(factory, name="Old stock", sort_order=20, is_active=False)
        a_model(factory, name="Chain block", category=lifting)
        a_model(factory, name="Pallet jack", category=lifting, is_published=False)
        session.commit()
        page = answered(list_categories(booking, administrator))
        assert set(page) == PAGE_MEMBERS
        assert [item["id"] for item in page["items"]] == [
            str(row.id) for row in (access, lifting, ladders, off, garden)
        ]
        assert (page["page"], page["pageSize"], page["total"]) == (1, 100, 5)
        listed = {item["name"]: item for item in page["items"]}
        assert set(listed["Lifting"]) == CATEGORY_MEMBERS
        assert (listed["Lifting"]["parentName"], listed["Lifting"]["modelCount"]) == (
            "Access and lifting",
            2,
        )
        assert (listed["Old stock"]["isActive"], listed["Access and lifting"]["modelCount"]) == (
            False,
            0,
        )

    def test_a_later_page_holds_the_rest(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        for order in range(3):
            a_category(factory, name=f"Category {order}", sort_order=order)
        session.commit()
        page = answered(list_categories(booking, administrator, page=2, pageSize=2))
        assert ([item["name"] for item in page["items"]], page["total"]) == (["Category 2"], 3)

    def test_a_page_larger_than_a_hundred_is_refused_naming_it(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = list_categories(booking, administrator, pageSize=101)
        assert refused_fields(response) == {"query.pageSize"}


class TestCreatingACategory:
    """A new category is active, answered 201, and recorded."""

    def test_a_category_is_created_and_its_audit_event_written(
        self, booking: BookingClient, session: Session, administrator: UserAccount
    ) -> None:
        body = created(create_category(booking, administrator, category_body()))
        assert set(body) == CATEGORY_MEMBERS
        assert (body["code"], body["isActive"], body["modelCount"], body["parentName"]) == (
            "PUMPS",
            True,
            0,
            None,
        )
        (event,) = events_of(session, body["id"])
        assert (event.action, event.actor_user_id) == ("category.created", administrator.id)
        assert event.after_state is not None and event.after_state["slug"] == "pumps-dewatering"

    def test_a_category_is_created_under_a_top_level_one(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        top = a_category(factory, name="Access")
        session.commit()
        body = created(
            create_category(booking, administrator, category_body(parentCategoryId=str(top.id)))
        )
        assert (body["parentCategoryId"], body["parentName"]) == (str(top.id), "Access")

    @pytest.mark.parametrize(
        ("members", "field"),
        [
            ({"code": "pumps"}, "body.code"),
            ({"slug": "Pumps Dewatering"}, "body.slug"),
            ({"name": "  "}, "body.name"),
            ({"sortOrder": -1}, "body.sortOrder"),
            ({"code": "X" * 17}, "body.code"),
            ({"isActive": False}, "body.isActive"),
        ],
    )
    def test_a_member_that_breaks_a_rule_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        administrator: UserAccount,
        members: dict[str, object],
        field: str,
    ) -> None:
        response = create_category(booking, administrator, category_body(**members))
        assert refused_fields(response) == {field}
        assert session.exec(select(Category)).all() == []

    def test_a_missing_code_is_refused_naming_it(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        body = category_body()
        del body["code"]
        assert refused_fields(create_category(booking, administrator, body)) == {"body.code"}

    @pytest.mark.parametrize(("member", "field"), [("code", "body.code"), ("slug", "body.slug")])
    def test_a_code_or_slug_another_category_holds_is_refused_naming_it(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        administrator: UserAccount,
        member: str,
        field: str,
    ) -> None:
        held = a_category(factory, name="Pumps")
        session.commit()
        value = held.code if member == "code" else held.slug
        response = create_category(booking, administrator, category_body(**{member: value}))
        assert refused_fields(response) == {field}

    def test_a_parent_that_is_itself_a_child_is_refused(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        child = a_category(factory, name="Ladders", parent=a_category(factory, name="Access"))
        session.commit()
        response = create_category(
            booking, administrator, category_body(parentCategoryId=str(child.id))
        )
        assert refused_fields(response) == {"body.parentCategoryId"}

    def test_a_parent_nobody_can_find_is_refused(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        body = category_body(parentCategoryId="00000000-0000-4000-8000-000000000000")
        assert refused_fields(create_category(booking, administrator, body)) == {
            "body.parentCategoryId"
        }


class TestEditingACategory:
    """An edit changes the members it names, and a category is switched off and never deleted."""

    def test_a_category_is_renamed_and_switched_off_with_one_event(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        category = a_category(factory, name="Pumps", description="Pumps.")
        session.commit()
        body = answered(
            edit_category(
                booking,
                administrator,
                category.id,
                {"name": "Pumps and dewatering", "isActive": False, "description": None},
            )
        )
        assert (body["name"], body["isActive"], body["description"]) == (
            "Pumps and dewatering",
            False,
            None,
        )
        (event,) = events_of(session, category.id)
        assert event.action == "category.updated"
        assert event.before_state == {"name": "Pumps", "description": "Pumps.", "is_active": True}

    def test_a_category_switched_off_leaves_the_public_list(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        category = a_category(factory, name="Pumps")
        session.commit()
        answered(edit_category(booking, administrator, category.id, {"isActive": False}))
        public = answered(booking.client.get("/api/catalogue/categories"))
        assert [item["code"] for item in public["items"]] == []

    def test_a_name_sent_as_null_is_refused_naming_it(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        category = a_category(factory, name="Pumps")
        session.commit()
        response = edit_category(booking, administrator, category.id, {"name": None})
        assert refused_fields(response) == {"body.name"}

    def test_a_category_with_children_cannot_be_put_under_another(
        self, booking: BookingClient, session: Session, factory: Factory, administrator: UserAccount
    ) -> None:
        access = a_category(factory, name="Access")
        a_category(factory, name="Ladders", parent=access)
        other = a_category(factory, name="Gardening")
        session.commit()
        response = edit_category(
            booking, administrator, access.id, {"parentCategoryId": str(other.id)}
        )
        assert refused_fields(response) == {"body.parentCategoryId"}

    def test_a_category_nobody_can_find_is_not_found(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = edit_category(
            booking, administrator, "00000000-0000-4000-8000-000000000000", {"name": "Pumps"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == "not-found"


class TestWhoMayCall:
    """Only an administrator. Counter staff and customers are refused with 403."""

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_staff_and_customers_are_refused_every_route(
        self, booking: BookingClient, session: Session, factory: Factory, role: UserRole
    ) -> None:
        branch = factory.branch() if role is UserRole.COUNTER_STAFF else None
        account = factory.user(role=role, branch=branch)
        category = a_category(factory, name="Pumps")
        session.commit()
        responses = [
            list_categories(booking, account),
            create_category(booking, account, category_body()),
            edit_category(booking, account, category.id, {"name": "Water"}),
        ]
        assert [response.status_code for response in responses] == [
            status.HTTP_403_FORBIDDEN
        ] * 3
