"""The customer's full personal data export (FR-28, US-27).

The export follows the personal data map, leaves credentials out, includes
staff-created events about the customer, excludes another customer, and
redacts staff actor metadata. The query runs against real SQL in the API tests.
"""

from __future__ import annotations

import json
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
from tests.support.clock import FixedClock
from tests.support.factories import Factory


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
