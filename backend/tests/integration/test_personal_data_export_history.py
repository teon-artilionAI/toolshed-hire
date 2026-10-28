"""Customer export history at a representative local volume (AUD-003).

This does not redesign the eager export. It proves the explicit audit subject
query remains one statement, includes the customer's history and excludes
another customer at 2,000 owned events. PostgreSQL is used because the query
relies on real subqueries and joins.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from decimal import Decimal
from ipaddress import ip_address
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel import Session

from app.domain.enums import RentalStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import AuditEvent, Rental
from app.infrastructure.personal_data_export import SqlPersonalDataExporter
from tests.support.factories import Factory

EVENT_COUNT = 2_000
OWNED_PROFILE_EVENTS = 1_000
OWNED_ASSET_EVENTS = 1_000
OTHER_PROFILE_EVENTS = 1_000
OTHER_ASSET_EVENTS = 1_000
OWNED_HIRE_REFERENCE = "TSH-H-26-009901"
OTHER_HIRE_REFERENCE = "TSH-H-26-009902"
ASSET_ID = uuid4()


@pytest.mark.postgres
class TestCustomerExportHistory:
    """Representative history does not change the audit subject query shape."""

    def test_two_thousand_owned_events_are_one_query_and_exclude_another_customer(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """The explicit subject query stays bounded and correctly scoped."""
        branch = postgres_factory.branch()
        customer = postgres_factory.user()
        profile = postgres_factory.customer_profile(branch=branch, account=customer)
        other = postgres_factory.user(email="other-export-history@example.co.za")
        other_profile = postgres_factory.customer_profile(branch=branch, account=other)
        staff = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
        at = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
        period = BookingPeriod(date(2026, 10, 20), date(2026, 10, 23))
        owned_reservation = postgres_factory.reservation(
            profile=profile, created_by=customer, branch=branch, period=period
        )
        other_reservation = postgres_factory.reservation(
            profile=other_profile, created_by=other, branch=branch, period=period
        )
        postgres_session.add_all(
            [
                Rental(
                    reference=OWNED_HIRE_REFERENCE,
                    reservation_id=owned_reservation.id,
                    branch_id=branch.id,
                    status=RentalStatus.SETTLED,
                    checked_out_at=at,
                    checked_out_by_user_id=staff.id,
                    due_back_on=period.end,
                    returned_at=at,
                    settled_at=at,
                    deposit_held=Decimal("0.00"),
                    agreement_signed=True,
                ),
                Rental(
                    reference=OTHER_HIRE_REFERENCE,
                    reservation_id=other_reservation.id,
                    branch_id=branch.id,
                    status=RentalStatus.SETTLED,
                    checked_out_at=at,
                    checked_out_by_user_id=staff.id,
                    due_back_on=period.end,
                    returned_at=at,
                    settled_at=at,
                    deposit_held=Decimal("0.00"),
                    agreement_signed=True,
                ),
            ]
        )
        postgres_session.flush()
        postgres_session.add_all(
            [
                AuditEvent(
                    occurred_at=at,
                    actor_user_id=staff.id,
                    actor_role=UserRole.COUNTER_STAFF,
                    entity_type="customer_profile",
                    entity_id=profile.id,
                    action="customer.history",
                    after_state={"step": number},
                    ip_address=ip_address("198.51.100.5"),
                )
                for number in range(OWNED_PROFILE_EVENTS)
            ]
            + [
                AuditEvent(
                    occurred_at=at,
                    actor_user_id=staff.id,
                    actor_role=UserRole.COUNTER_STAFF,
                    entity_type="asset",
                    entity_id=ASSET_ID,
                    action="asset.status_changed",
                    after_state={
                        "status": "ON_HIRE",
                        "rental_reference": OWNED_HIRE_REFERENCE,
                        "step": number,
                    },
                    ip_address=ip_address("198.51.100.5"),
                )
                for number in range(OWNED_ASSET_EVENTS)
            ]
            + [
                AuditEvent(
                    occurred_at=at,
                    actor_user_id=staff.id,
                    actor_role=UserRole.COUNTER_STAFF,
                    entity_type="customer_profile",
                    entity_id=other_profile.id,
                    action="customer.history.other",
                    after_state={"step": number},
                    ip_address=ip_address("198.51.100.6"),
                )
                for number in range(OTHER_PROFILE_EVENTS)
            ]
            + [
                AuditEvent(
                    occurred_at=at,
                    actor_user_id=staff.id,
                    actor_role=UserRole.COUNTER_STAFF,
                    entity_type="asset",
                    entity_id=ASSET_ID,
                    action="asset.status_changed",
                    after_state={
                        "status": "ON_HIRE",
                        "rental_reference": OTHER_HIRE_REFERENCE,
                        "step": number,
                    },
                    ip_address=ip_address("198.51.100.6"),
                )
                for number in range(OTHER_ASSET_EVENTS)
            ]
        )
        postgres_session.commit()

        statements: list[str] = []

        def record_audit_query(conn, cursor, statement, parameters, context, executemany):
            if "audit_event" in statement:
                statements.append(statement)

        engine = postgres_session.bind
        event.listen(engine, "before_cursor_execute", record_audit_query)
        started = time.perf_counter()
        try:
            exported = SqlPersonalDataExporter(postgres_session).export(
                customer_profile_id=profile.id, user_account_id=customer.id
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_audit_query)
        elapsed = time.perf_counter() - started
        print(
            f"export history: rows={len(exported['audit_event'])} "
            f"audit_queries={len(statements)} elapsed={elapsed:.3f}s"
        )

        rows = exported["audit_event"]
        asset_rows = [row for row in rows if row["entity_type"] == "asset"]
        assert len(rows) == EVENT_COUNT
        assert len(asset_rows) == OWNED_ASSET_EVENTS
        assert len(statements) == 1
        assert all(
            row["entity_id"] in {str(profile.id), str(ASSET_ID)} for row in rows
        )
        assert all(
            row["after_state"]["rental_reference"] == OWNED_HIRE_REFERENCE
            for row in asset_rows
        )
        assert all(OTHER_HIRE_REFERENCE not in str(row) for row in rows)
        assert all(row["actor_user_id"] is None for row in rows)
        assert all(row["ip_address"] is None for row in rows)
        assert elapsed < 5.0
