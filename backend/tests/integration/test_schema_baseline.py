"""The database the migration builds is the database the design document describes.

Alembic autogenerate does not write an extension, an exclusion constraint or a
partial index, so the baseline migration is written by hand. Hand written DDL
can be wrong quietly. A missing extension, a constraint with a looser
definition or an index that lost its WHERE clause would not fail a single
behavioural test until the day it mattered. This file reads the PostgreSQL
catalogue directly and says what has to be there.

It runs before every other test in the suite. The ordering is done by the
collection hook in tests/integration/conftest.py, not by the file name, so the
reason sits next to the mechanism. Every other integration test assumes the
schema below, and a failure here explains all of theirs.

The expected names come from app.infrastructure.schema_ddl and app.domain.enums,
which are the application's statement of the schema. The migration has its own
frozen statement under alembic/baseline and imports neither. Comparing the two
through the live catalogue is what stops them drifting apart.

The models class does the same for the SQLModel classes. Most of the seventeen
tables have no flow written against them yet, so a misspelt column on one of
those models would otherwise wait for the feature that first used it.

The last class checks the columns later revisions added to a baseline table.
Each one is NOT NULL with a default, and the default is what lets the release
before the revision go on inserting rows that never name the column.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlmodel import Session, SQLModel

from app.infrastructure import models
from app.infrastructure.schema_ddl import (
    ALLOCATION_TABLE,
    COLUMNS_ADDED_AFTER_BASELINE,
    ENUM_TYPES,
    OVERLAP_CONSTRAINT_DEFINITION,
    OVERLAP_CONSTRAINT_NAME,
    PARTIAL_INDEX_NAMES,
    REQUIRED_EXTENSIONS,
    TABLE_NAMES,
)
from tests.support.pg import (
    column_default,
    column_nullability,
    constraint_definition,
    enum_type_labels,
    exclusion_constraint_names,
    installed_extensions,
    partial_index_predicates,
    table_names,
)

pytestmark = pytest.mark.postgres

DOCUMENTED_TABLE_COUNT: Final[int] = 17
DOCUMENTED_ENUM_TYPE_COUNT: Final[int] = 17
DOCUMENTED_EXTENSIONS: Final[frozenset[str]] = frozenset({"btree_gist", "citext", "pg_trgm"})


class TestTheExtensionsExist:
    """Nothing else in the schema can be created without these three."""

    def test_the_application_declares_exactly_the_three_documented_extensions(self) -> None:
        assert frozenset(REQUIRED_EXTENSIONS) == DOCUMENTED_EXTENSIONS

    @pytest.mark.parametrize("extension", sorted(DOCUMENTED_EXTENSIONS))
    def test_the_extension_is_installed_after_the_migration(
        self, postgres_session: Session, extension: str
    ) -> None:
        installed = installed_extensions(postgres_session)
        assert extension in installed, (
            f"The migration did not leave {extension} installed. Found {sorted(installed)}."
        )


class TestTheSeventeenTablesExist:
    """Sixteen domain tables and rate_limit_counter, under their singular names."""

    def test_the_application_lists_seventeen_distinct_tables(self) -> None:
        assert len(TABLE_NAMES) == DOCUMENTED_TABLE_COUNT
        assert len(set(TABLE_NAMES)) == DOCUMENTED_TABLE_COUNT

    def test_every_documented_table_was_created(self, postgres_session: Session) -> None:
        found = table_names(postgres_session)
        missing = sorted(set(TABLE_NAMES) - found)
        assert not missing, (
            f"The migration did not create {missing}. The schema holds {sorted(found)}."
        )


class TestTheEnumeratedTypesMatchTheDomain:
    """A member the database type lacks is a value the application cannot store."""

    def test_the_domain_declares_seventeen_enumerated_types(self) -> None:
        assert len(ENUM_TYPES) == DOCUMENTED_ENUM_TYPE_COUNT

    def test_every_enumerated_type_holds_the_members_the_domain_declares(
        self, postgres_session: Session
    ) -> None:
        stored = enum_type_labels(postgres_session)
        differing = {
            type_name: {"domain": members, "database": stored.get(type_name)}
            for type_name, members in ENUM_TYPES.items()
            if stored.get(type_name) != members
        }
        assert not differing, (
            "The database enumerated types disagree with the domain enumerations. "
            f"Differences: {differing}."
        )


class TestTheExclusionConstraintIsTheDocumentedOne:
    """The constraint that removes double booking, by name and by definition."""

    def test_the_constraint_exists_on_asset_allocation_as_an_exclusion_constraint(
        self, postgres_session: Session
    ) -> None:
        names = exclusion_constraint_names(postgres_session, ALLOCATION_TABLE)
        assert OVERLAP_CONSTRAINT_NAME in names, (
            "The exclusion constraint the whole design depends on is absent. Found "
            f"exclusion constraints {sorted(names)} on {ALLOCATION_TABLE}."
        )

    def test_the_constraint_has_the_documented_definition(self, postgres_session: Session) -> None:
        """Same asset, overlapping half open ranges, active rows only.

        A constraint of the right name with a closed upper bound, or with no
        partial predicate, would pass an existence check and still be wrong.
        """
        definition = constraint_definition(
            postgres_session, ALLOCATION_TABLE, OVERLAP_CONSTRAINT_NAME
        )
        assert definition == OVERLAP_CONSTRAINT_DEFINITION, (
            f"{OVERLAP_CONSTRAINT_NAME} is not the documented constraint. Expected "
            f"{OVERLAP_CONSTRAINT_DEFINITION!r} and the database holds {definition!r}."
        )


class TestThePartialIndexesExist:
    """A partial index that became a full one still works, which is why it is checked."""

    @pytest.mark.parametrize("index_name", PARTIAL_INDEX_NAMES)
    def test_the_index_exists_and_carries_a_predicate(
        self, postgres_session: Session, index_name: str
    ) -> None:
        predicates = partial_index_predicates(postgres_session)
        assert index_name in predicates, (
            f"{index_name} is missing or is no longer partial. The partial indexes in the "
            f"schema are {sorted(predicates)}."
        )


class TestTheModelsMatchTheMigratedTables:
    """The models and the migration are written separately, so they are compared."""

    def test_there_is_one_model_for_every_documented_table(self) -> None:
        assert set(SQLModel.metadata.tables) == set(TABLE_NAMES)

    def test_the_models_package_re_exports_every_model(self) -> None:
        """`from app.infrastructure.models import X` has to work for all seventeen."""
        exported_tables = {getattr(models, name).__tablename__ for name in models.__all__}
        assert exported_tables == set(TABLE_NAMES)

    @pytest.mark.parametrize("table_name", TABLE_NAMES)
    def test_the_model_declares_the_columns_the_migration_created(
        self, postgres_session: Session, table_name: str
    ) -> None:
        """Same column names and the same nullability, table by table."""
        declared = {
            column.name: bool(column.nullable)
            for column in SQLModel.metadata.tables[table_name].columns
        }
        created = column_nullability(postgres_session, table_name)
        only_on_model = sorted(set(declared) - set(created))
        only_in_database = sorted(set(created) - set(declared))
        nullability_differs = sorted(
            name for name in set(declared) & set(created) if declared[name] != created[name]
        )
        assert declared == created, (
            f"The model for {table_name} and the migrated table disagree. The model alone "
            f"declares {only_on_model}, the database alone holds {only_in_database}, and "
            f"nullability differs on {nullability_differs}."
        )


class TestTheColumnsAddedAfterTheBaseline:
    """A column a later revision adds is NOT NULL with the default the application expects."""

    @pytest.mark.parametrize(
        ("table_name", "column_name", "default"),
        COLUMNS_ADDED_AFTER_BASELINE,
        ids=[f"{table}.{column}" for table, column, _default in COLUMNS_ADDED_AFTER_BASELINE],
    )
    def test_the_column_is_not_null_and_carries_its_default(
        self, postgres_session: Session, table_name: str, column_name: str, default: str
    ) -> None:
        nullable = column_nullability(postgres_session, table_name).get(column_name)
        found = column_default(postgres_session, table_name, column_name)
        assert (nullable, found) == (False, default), (
            f"{table_name}.{column_name} should be NOT NULL with the default {default!r}. "
            f"The database says nullable={nullable} and default={found!r}."
        )
