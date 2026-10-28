"""Every table is in the personal data map, and the map agrees with the schema.

The export of a customer's data, the anonymising routine and the register of
processing all read the map. A table added later that holds customer data and
is missing from it would be left out of all three without anybody noticing, so
these tests fail the pull request that adds it instead.
"""

from __future__ import annotations

from collections import deque
from typing import Final

import pytest
from sqlalchemy import Table
from sqlmodel import SQLModel

import app.infrastructure.models  # noqa: F401  # registers every table on the metadata
from app.infrastructure.personal_data_map import (
    ITSELF,
    PERSONAL_DATA_MAP,
    CustomerData,
    NoCustomerData,
    customer_data_tables,
)

# The two tables a person's details live in. Anything that leads to one of them
# through its foreign keys is about a person.
PERSON_TABLES: Final[frozenset[str]] = frozenset({"customer_profile", "user_account"})


def tables() -> dict[str, Table]:
    """Return every table the models declare, by name."""
    return dict(SQLModel.metadata.tables)


def reaches_a_person(name: str) -> bool:
    """Return True when a table leads to a person table through its foreign keys."""
    schema = tables()
    seen: set[str] = set()
    queue = deque([name])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for key in schema[current].foreign_keys:
            parent = key.column.table.name
            if parent in PERSON_TABLES:
                return True
            queue.append(parent)
    return False


class TestTheMapCoversTheSchema:
    """A table missing from the map is a table nobody decided about."""

    def test_every_table_in_the_schema_is_in_the_map(self) -> None:
        missing = sorted(set(tables()) - set(PERSONAL_DATA_MAP))
        assert not missing, (
            f"{missing} are not in app/infrastructure/personal_data_map.py. Classify each as "
            "CustomerData or NoCustomerData in the pull request that adds it."
        )

    def test_the_map_names_no_table_the_schema_lacks(self) -> None:
        assert not sorted(set(PERSONAL_DATA_MAP) - set(tables()))


class TestTheForeignKeysAgree:
    """A table that leads to a person through its keys holds something about them."""

    @pytest.mark.parametrize("name", sorted(PERSONAL_DATA_MAP))
    def test_a_table_that_reaches_a_person_is_customer_data_or_says_why_not(
        self, name: str
    ) -> None:
        kind = PERSONAL_DATA_MAP[name]
        if isinstance(kind, NoCustomerData) and reaches_a_person(name):
            assert kind.staff_link_only, (
                f"{name} reaches a customer profile or a user account through its foreign "
                "keys, and the map says it holds no customer data. Mark it CustomerData, or "
                "staff_link_only with the reason if only staff accounts are linked."
            )


class TestTheColumnsExist:
    """A misspelt column would be skipped by the export and by the anonymising routine."""

    @pytest.mark.parametrize("name", customer_data_tables())
    def test_every_named_column_is_a_column_of_the_table(self, name: str) -> None:
        kind = PERSONAL_DATA_MAP[name]
        assert isinstance(kind, CustomerData)
        columns = {column.name for column in tables()[name].columns}
        named = {*kind.identifying_columns, *kind.free_text_columns}
        assert named <= columns, f"{name} has no column {sorted(named - columns)}"

    @pytest.mark.parametrize("name", customer_data_tables())
    def test_the_link_to_the_customer_is_a_foreign_key_of_the_table(self, name: str) -> None:
        kind = PERSONAL_DATA_MAP[name]
        assert isinstance(kind, CustomerData)
        if kind.reached_through == ITSELF:
            assert name in PERSON_TABLES
            return
        keyed = {key.parent.name for key in tables()[name].foreign_keys}
        assert kind.reached_through in keyed, (
            f"{name}.{kind.reached_through} is not a foreign key, so it cannot lead to the customer"
        )


class TestTheChecksCatchAMistake:
    """The tests above would pass on an empty schema, so the walk is checked on its own."""

    def test_a_booking_reaches_a_person_and_the_catalogue_does_not(self) -> None:
        assert reaches_a_person("rental_item")
        assert not reaches_a_person("product_model")
