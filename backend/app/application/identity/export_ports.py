"""The port through which a customer's own data is read for export (FR-28, US-27).

The export is built from the personal data map, so the set of tables and the
columns that identify a customer are classified in one place. An
implementation reads each table the map marks as the customer's, from the
customer's profile and account outwards, and answers JSON-ready values.

The port deliberately says nothing about how the tables are found. The SQL
implementation follows the foreign keys, which means a table added later is
exported as soon as the map classifies it and its key chain exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

# A table's rows, each a mapping from column name to a JSON-ready value.
type ExportedRows = tuple[Mapping[str, JsonValue], ...]


class PersonalDataExporter(Protocol):
    """Reads every table that holds one customer's data."""

    def export(
        self, *, customer_profile_id: UUID, user_account_id: UUID
    ) -> Mapping[str, ExportedRows]:
        """Return the customer's rows, by table name, in the order of the personal data map.

        Args:
            customer_profile_id: The customer profile whose records are exported.
            user_account_id: The sign in account behind the profile.

        """
        ...


__all__ = ["ExportedRows", "JsonScalar", "JsonValue", "PersonalDataExporter"]
