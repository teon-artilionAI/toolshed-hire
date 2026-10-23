"""The SQL export of one customer's data, following the personal data map.

For every table the map classifies as holding customer data, this module finds
the shortest foreign key path from that table to the customer profile, and
falls back to the user account for the tables that hang off the account
itself. It then reads the table's columns, except the credential columns that
must never leave the service, and returns JSON-ready values.

The path is derived from the metadata, so a table added later is exported as
soon as the map classifies it and its key chain reaches the customer. A table
the map classifies as customer data but which has no path raises at export
time rather than silently returning nothing, because an incomplete answer to
a right of access is worse than a loud failure.

This is deliberately not a per-table list. The map owns the classification,
and this module owns only the traversal and the JSON conversion.
"""

from __future__ import annotations

import base64
import logging
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv6Address
from typing import Final, cast
from uuid import UUID

from sqlalchemy import Column, Select, Table
from sqlmodel import Session, SQLModel

from app.application.identity.export_ports import ExportedRows, JsonValue, PersonalDataExporter
from app.infrastructure.personal_data_map import PERSONAL_DATA_MAP, CustomerData

logger = logging.getLogger(__name__)

# Columns that hold a credential or a one way token and must never be exported.
SECRET_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "password_hash",
        "email_verification_token_hash",
        "password_reset_token_hash",
        "token_hash",
    }
)
CUSTOMER_PROFILE_TABLE: Final[str] = "customer_profile"
USER_ACCOUNT_TABLE: Final[str] = "user_account"
# The tables that hang off the account rather than the customer profile.
ACCOUNT_ROOTED_TABLES: Final[frozenset[str]] = frozenset(
    {USER_ACCOUNT_TABLE, "refresh_session", "audit_event"}
)


class SqlPersonalDataExporter(PersonalDataExporter):
    """Reads a customer's rows from every table the personal data map names."""

    def __init__(self, session: Session) -> None:
        """Bind the exporter to the session of its unit of work."""
        self._session = session
        self._tables = SQLModel.metadata.tables

    def export(
        self, *, customer_profile_id: UUID, user_account_id: UUID
    ) -> Mapping[str, ExportedRows]:
        """Return the customer's rows, by table name, in the order of the map."""
        exported: dict[str, ExportedRows] = {}
        for table_name, classification in PERSONAL_DATA_MAP.items():
            if not isinstance(classification, CustomerData):
                continue
            exported[table_name] = self._rows_of(
                table_name, customer_profile_id, user_account_id
            )
        logger.info(
            "customer.export_read",
            extra={
                "table_count": len(exported),
                "row_count": sum(len(rows) for rows in exported.values()),
            },
        )
        return exported

    def _rows_of(
        self, table_name: str, customer_profile_id: UUID, user_account_id: UUID
    ) -> ExportedRows:
        """Return every row of one table that belongs to the customer."""
        table = self._tables.get(table_name)
        if table is None:
            raise RuntimeError(
                f"The personal data map names table {table_name}, and the metadata does not "
                "define it. Every customer data table must exist in the ORM metadata."
            )
        root_name = self._root_for(table_name)
        path = _path_to(table, root_name)
        if path is None:
            raise RuntimeError(
                f"The personal data map classifies {table_name} as customer data, and there is "
                f"no foreign key path from it to {root_name}. Add the missing key or correct "
                "the classification."
            )
        columns = [column for column in table.columns if column.name not in SECRET_COLUMNS]
        statement = _select_from(table, columns, path)
        root_table = self._tables[root_name]
        root_value = customer_profile_id if root_name == CUSTOMER_PROFILE_TABLE else user_account_id
        statement = statement.where(root_table.c["id"] == root_value)
        order = [table.c[column.name] for column in table.primary_key.columns]
        if order:
            statement = statement.order_by(*order)
        rows = self._session.execute(statement).mappings().all()
        return tuple(
            {name: _json_value(value) for name, value in row.items()} for row in rows
        )

    def _root_for(self, table_name: str) -> str:
        """Return the table the customer's rows are reached through."""
        if table_name in ACCOUNT_ROOTED_TABLES:
            return USER_ACCOUNT_TABLE
        if table_name == CUSTOMER_PROFILE_TABLE:
            return CUSTOMER_PROFILE_TABLE
        return CUSTOMER_PROFILE_TABLE


def _select_from(
    table: Table, columns: Sequence[Column[object]], path: Sequence[_Edge]
) -> Select[tuple[object, ...]]:
    """Return the select of a table's columns, joined along the key path."""
    statement = _select_columns(columns).select_from(table)
    for edge in path:
        statement = statement.join(edge.target, edge.local == edge.remote)
    return statement


def _select_columns(columns: Sequence[Column[object]]) -> Select[tuple[object, ...]]:
    """Return a select of the columns, using a literal when a table has none left."""
    from sqlalchemy import literal, select

    if not columns:
        return cast(Select[tuple[object, ...]], select(literal(1).label("empty")))
    return select(*columns)


class _Edge:
    """One foreign key step on the way from a table to the root."""

    __slots__ = ("local", "remote", "target")

    def __init__(self, local: Column[object], remote: Column[object], target: Table) -> None:
        self.local = local
        self.remote = remote
        self.target = target


def _path_to(table: Table, root_name: str) -> tuple[_Edge, ...] | None:
    """Return the shortest foreign key path from a table to the root, or None."""
    if table.name == root_name:
        return ()
    queue: deque[tuple[Table, tuple[_Edge, ...]]] = deque([(table, ())])
    visited = {table.name}
    while queue:
        current, path = queue.popleft()
        for foreign_key in current.foreign_keys:
            constraint = foreign_key.constraint
            if constraint is None or len(constraint.columns) != 1:
                continue
            target = foreign_key.column.table
            if target.name in visited:
                continue
            edge = _Edge(foreign_key.parent, foreign_key.column, target)
            if target.name == root_name:
                return (*path, edge)
            visited.add(target.name)
            queue.append((target, (*path, edge)))
    return None


def _json_value(value: object) -> JsonValue:
    """Return a database value as something JSON can carry."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal | UUID | IPv4Address | IPv6Address):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bytes | bytearray | memoryview):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence):
        return [_json_value(item) for item in value]
    return str(value)


__all__ = ["SECRET_COLUMNS", "SqlPersonalDataExporter"]
