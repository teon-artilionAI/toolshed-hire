"""Customer export history at a representative local volume (AUD-003).

This does not redesign the eager export. It proves the explicit audit subject
query remains one statement, includes the customer's history and excludes
another customer at 2,000 owned events. PostgreSQL is used because the query
relies on real subqueries and joins.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from ipaddress import ip_address

import pytest
from sqlalchemy import event
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent
from app.infrastructure.personal_data_export import SqlPersonalDataExporter
from tests.support.factories import Factory

EVENT_COUNT = 2_000


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
        postgres_session.commit()
        at = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
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
                for number in range(EVENT_COUNT)
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
                for number in range(EVENT_COUNT)
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

        assert len(exported["audit_event"]) == EVENT_COUNT
        assert len(statements) == 1
        assert all(row["entity_id"] == str(profile.id) for row in exported["audit_event"])
        assert all(row["actor_user_id"] is None for row in exported["audit_event"])
        assert all(row["ip_address"] is None for row in exported["audit_event"])
        assert elapsed < 5.0
