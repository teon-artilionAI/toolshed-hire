"""The customer's full personal data export (FR-28, US-27).

The export follows the personal data map, leaves credentials out, includes
staff-created events about the customer, excludes another customer, and
redacts staff actor metadata. The query runs against real SQL in the API tests.
"""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.domain.enums import UserRole
from app.infrastructure.models import (
    AuditEvent,
    Branch,
    Charge,
    CustomerProfile,
    UserAccount,
)
from tests.api.test_statement_and_export import (
    CHECKOUT,
    EXPORT_PATH,
    add_rental,
    bearer,
)
from tests.support.booking_api import BookingClient, answered, build_booking_world, created
from tests.support.checkout_api import checked_out
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.rental_api import item_ids, on_hire, return_body, take_back


@pytest.fixture
def customer(
    session: Session, factory: Factory, home_branch: Branch
) -> tuple[UserAccount, CustomerProfile]:
    """Return a committed customer with a profile at the home branch."""
    account = factory.user()
    profile = factory.customer_profile(branch=home_branch, account=account)
    session.commit()
    return account, profile


def test_the_export_has_every_customer_table_and_no_credentials(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch: Branch,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """The export follows the personal data map and leaves secrets out."""
    account, profile = customer
    add_rental(session, factory, account=account, profile=profile, branch=home_branch)

    response = account_api.get(EXPORT_PATH, headers=bearer(account, still_clock))

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="toolshed-my-data-'
    )
    body = response.json()
    tables = body["tables"]
    assert "customer_profile" in tables
    assert "user_account" in tables
    assert "reservation" in tables
    assert "rental" in tables
    assert "charge" in tables
    assert len(tables["rental"]) == 1
    assert len(tables["charge"]) == 2
    assert body["rowCount"] == sum(len(rows) for rows in tables.values())
    flattened = json.dumps(body)
    assert "password_hash" not in flattened
    assert "token_hash" not in flattened
    assert "email_verification_token_hash" not in flattened


def test_the_export_includes_customer_subjects_and_redacts_staff_actors(
    account_api: TestClient,
    session: Session,
    factory: Factory,
    home_branch: Branch,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """Staff events about the customer are exported, without the staff actor's details."""
    account, profile = customer
    rental = add_rental(session, factory, account=account, profile=profile, branch=home_branch)
    charge = session.exec(select(Charge).where(col(Charge.rental_id) == rental.id)).first()
    assert charge is not None
    staff = factory.user(role=UserRole.COUNTER_STAFF, branch=home_branch)
    other_account = factory.user(email="other-export@example.co.za")
    other_profile = factory.customer_profile(branch=home_branch, account=other_account)
    session.commit()

    def add_event(
        entity_type: str,
        entity_id,
        action: str,
        *,
        actor: UserAccount | None,
        ip_address: str | None = None,
        request_id=None,
    ) -> None:
        session.add(
            AuditEvent(
                occurred_at=CHECKOUT,
                actor_user_id=actor.id if actor is not None else None,
                actor_role=actor.role if actor is not None else None,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                ip_address=ip_address,
                request_id=request_id,
                after_state={"reason": "audit export test"},
            )
        )

    add_event(
        "user_account", account.id, "customer.signed_in", actor=account,
        ip_address="192.0.2.10", request_id=uuid4(),
    )
    add_event(
        "customer_profile", profile.id, "customer.trade_discount_changed", actor=staff,
        ip_address="198.51.100.5", request_id=uuid4(),
    )
    add_event(
        "reservation", rental.reservation_id, "reservation.confirmed", actor=staff,
        ip_address="198.51.100.5",
    )
    add_event("rental", rental.id, "rental.checked_out", actor=staff, ip_address="198.51.100.5")
    add_event("charge", charge.id, "charge.corrected", actor=staff, ip_address="198.51.100.5")
    add_event("reservation", rental.reservation_id, "reservation.expired", actor=None)
    add_event(
        "customer_profile", other_profile.id, "customer.trade_discount_changed", actor=staff,
        ip_address="198.51.100.6",
    )
    add_event("asset", uuid4(), "asset.status_changed", actor=staff, ip_address="198.51.100.7")
    session.commit()

    response = account_api.get(EXPORT_PATH, headers=bearer(account, still_clock))

    assert response.status_code == status.HTTP_200_OK
    rows = response.json()["tables"]["audit_event"]
    by_action = {row["action"]: row for row in rows}
    assert set(by_action) == {
        "customer.signed_in",
        "customer.trade_discount_changed",
        "reservation.confirmed",
        "rental.checked_out",
        "charge.corrected",
        "reservation.expired",
    }
    own = by_action["customer.signed_in"]
    assert own["actor_user_id"] == str(account.id)
    assert own["actor_role"] == "CUSTOMER"
    assert own["ip_address"] == "192.0.2.10"
    assert own["request_id"] is not None
    for action in (
        "customer.trade_discount_changed",
        "reservation.confirmed",
        "rental.checked_out",
        "charge.corrected",
        "reservation.expired",
    ):
        row = by_action[action]
        assert row["actor_user_id"] is None
        assert row["actor_role"] is None
        assert row["ip_address"] is None
        assert row["request_id"] is None
    assert "other-export@example.co.za" not in json.dumps(response.json())


def test_the_export_is_audited_and_only_names_counts(
    account_api: TestClient,
    session: Session,
    still_clock: FixedClock,
    customer: tuple[UserAccount, CustomerProfile],
) -> None:
    """An export writes one event with counts, never the values."""
    account, _profile = customer
    response = account_api.get(EXPORT_PATH, headers=bearer(account, still_clock))
    assert response.status_code == status.HTTP_200_OK
    from app.infrastructure.models import AuditEvent

    session.expire_all()
    events = list(
        session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "customer.data_exported")
        ).all()
    )
    assert len(events) == 1
    assert events[0].after_state == {
        "table_count": len(response.json()["tables"]),
        "row_count": response.json()["rowCount"],
    }


def test_actual_checkout_and_return_asset_events_are_owned_and_scoped(
    booking: BookingClient,
    account_api: TestClient,
    session: Session,
    factory: Factory,
    still_clock: FixedClock,
) -> None:
    """The actual hire producers export only this customer's hire-linked asset events."""
    world = build_booking_world(factory, asset_count=1)
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    other = factory.user(email="other-shared-asset@example.co.za")
    factory.customer_profile(branch=world.branch, account=other)
    session.commit()

    first = on_hire(booking, world, assistant)
    answered(take_back(booking, assistant, first["id"], return_body(*item_ids(first))))

    booking.clock.advance(timedelta(days=7))
    second_draft = created(booking.create(other, world.payload()))
    answered(booking.hold(other, second_draft["id"]))
    answered(booking.confirm(assistant, second_draft["id"]))
    second = checked_out(booking, assistant, second_draft["id"])
    answered(take_back(booking, assistant, second["id"], return_body(*item_ids(second))))

    unrelated_asset_id = uuid4()
    session.add(
        AuditEvent(
            occurred_at=booking.clock.now(),
            actor_user_id=assistant.id,
            actor_role=assistant.role,
            entity_type="asset",
            entity_id=unrelated_asset_id,
            action="asset.status_changed",
            after_state={"status": "AVAILABLE"},
            ip_address="198.51.100.8",
        )
    )
    session.commit()

    response = account_api.get(EXPORT_PATH, headers=bearer(world.customer, still_clock))

    assert response.status_code == status.HTTP_200_OK
    asset_rows = [
        row for row in response.json()["tables"]["audit_event"] if row["entity_type"] == "asset"
    ]
    assert len(asset_rows) == 2
    assert {row["after_state"]["status"] for row in asset_rows} == {"ON_HIRE", "AVAILABLE"}
    assert all(row["entity_id"] == str(world.assets[0].id) for row in asset_rows)
    assert all(row["after_state"]["rental_reference"] == first["reference"] for row in asset_rows)
    exported = json.dumps(response.json())
    assert str(second["reference"]) not in exported
    assert str(unrelated_asset_id) not in exported
    for row in asset_rows:
        assert row["actor_user_id"] is None
        assert row["actor_role"] is None
        assert row["ip_address"] is None
        assert row["request_id"] is None
