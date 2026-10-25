"""The audit-event part of a customer's personal data export.

The audit table is polymorphic. A customer's own events have the customer as
actor, while a staff event about the customer names the customer profile, a
booking, a hire, a charge, a damage report or a notification as its subject.
The subject types are explicit in the personal data map. A staff actor's id,
role, address and request id are not the customer's data and are redacted.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, Table, and_, or_, select
from sqlalchemy.engine import RowMapping
from sqlmodel import Session

from app.infrastructure.personal_data_map import PERSONAL_DATA_MAP, CustomerData

AUDIT_EVENT_TABLE: Final[str] = "audit_event"
STAFF_REDACTED_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "actor_user_id",
    "actor_role",
    "ip_address",
    "request_id",
)


def audit_rows(
    session: Session,
    tables: Mapping[str, Table],
    customer_profile_id: UUID,
    user_account_id: UUID,
) -> tuple[dict[str, object], ...]:
    """Return the audit events whose subject is this customer."""
    table = tables[AUDIT_EVENT_TABLE]
    kind = PERSONAL_DATA_MAP[AUDIT_EVENT_TABLE]
    if not isinstance(kind, CustomerData):
        raise RuntimeError("The audit_event table must be classified as customer data.")
    builders: dict[str, Callable[[], ColumnElement[bool]]] = {
        "user_account": lambda: and_(
            table.c["entity_type"] == "user_account",
            table.c["entity_id"] == user_account_id,
        ),
        "customer_profile": lambda: and_(
            table.c["entity_type"] == "customer_profile",
            table.c["entity_id"] == customer_profile_id,
        ),
        "reservation": lambda: and_(
            table.c["entity_type"] == "reservation",
            table.c["entity_id"].in_(_reservation_ids(tables, customer_profile_id)),
        ),
        "rental": lambda: and_(
            table.c["entity_type"] == "rental",
            table.c["entity_id"].in_(_rental_ids(tables, customer_profile_id)),
        ),
        "charge": lambda: and_(
            table.c["entity_type"] == "charge",
            table.c["entity_id"].in_(_charge_ids(tables, customer_profile_id)),
        ),
        "damage_report": lambda: and_(
            table.c["entity_type"] == "damage_report",
            table.c["entity_id"].in_(_damage_ids(tables, customer_profile_id)),
        ),
        "notification": lambda: and_(
            table.c["entity_type"] == "notification",
            table.c["entity_id"].in_(_notification_ids(tables, customer_profile_id)),
        ),
    }
    conditions = [table.c["actor_user_id"] == user_account_id]
    for entity_type in kind.subject_entity_types:
        build = builders.get(entity_type)
        if build is None:
            raise RuntimeError(
                f"The personal data map names audit subject {entity_type}, and the "
                "exporter has no subject query for it. Add the query or remove the map entry."
            )
        conditions.append(build())
    columns = list(table.columns)
    statement = (
        select(*columns)
        .select_from(table)
        .where(or_(*conditions))
        .order_by(table.c["id"])
    )
    return tuple(
        _redact(row, user_account_id)
        for row in session.execute(statement).mappings().all()
    )


def _reservation_ids(tables: Mapping[str, Table], customer_profile_id: UUID) -> Select[tuple[UUID]]:
    reservations = tables["reservation"]
    return select(reservations.c["id"]).where(
        reservations.c["customer_profile_id"] == customer_profile_id
    )


def _rental_ids(tables: Mapping[str, Table], customer_profile_id: UUID) -> Select[tuple[UUID]]:
    rentals = tables["rental"]
    reservations = tables["reservation"]
    return (
        select(rentals.c["id"])
        .select_from(rentals)
        .join(reservations, rentals.c["reservation_id"] == reservations.c["id"])
        .where(reservations.c["customer_profile_id"] == customer_profile_id)
    )


def _charge_ids(tables: Mapping[str, Table], customer_profile_id: UUID) -> Select[tuple[UUID]]:
    charges = tables["charge"]
    rentals = tables["rental"]
    reservations = tables["reservation"]
    return (
        select(charges.c["id"])
        .select_from(charges)
        .join(rentals, charges.c["rental_id"] == rentals.c["id"])
        .join(reservations, rentals.c["reservation_id"] == reservations.c["id"])
        .where(reservations.c["customer_profile_id"] == customer_profile_id)
    )


def _damage_ids(tables: Mapping[str, Table], customer_profile_id: UUID) -> Select[tuple[UUID]]:
    reports = tables["damage_report"]
    items = tables["rental_item"]
    rentals = tables["rental"]
    reservations = tables["reservation"]
    return (
        select(reports.c["id"])
        .select_from(reports)
        .join(items, reports.c["rental_item_id"] == items.c["id"])
        .join(rentals, items.c["rental_id"] == rentals.c["id"])
        .join(reservations, rentals.c["reservation_id"] == reservations.c["id"])
        .where(reservations.c["customer_profile_id"] == customer_profile_id)
    )


def _notification_ids(
    tables: Mapping[str, Table], customer_profile_id: UUID
) -> Select[tuple[UUID]]:
    notifications = tables["notification"]
    reservations = tables["reservation"]
    return (
        select(notifications.c["id"])
        .select_from(notifications)
        .join(reservations, notifications.c["reservation_id"] == reservations.c["id"])
        .where(reservations.c["customer_profile_id"] == customer_profile_id)
    )


def _redact(row: RowMapping, user_account_id: UUID) -> dict[str, object]:
    values = dict(row)
    if values.get("actor_user_id") != user_account_id:
        for column in STAFF_REDACTED_AUDIT_COLUMNS:
            if column in values:
                values[column] = None
    return values


__all__ = ["AUDIT_EVENT_TABLE", "audit_rows"]
