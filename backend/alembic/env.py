"""Alembic environment.

The connection string comes from the application settings, which read
DATABASE_URL from the environment. It is never written into alembic.ini,
because a file with a password in it eventually gets committed.

Autogenerate is available for ordinary column work, but the migration that
matters here is hand written. Autogenerate cannot invent an exclusion
constraint, and a schema whose defining invariant is invisible to the tool that
maintains it must be written out by hand and read by a human.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context
from app.config import settings
from app.infrastructure import models  # noqa: F401  imported for its side effect

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Set here rather than in alembic.ini so no credential is ever committed.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting, for review before a release."""
    logger.info("Running migrations offline against %s", _safe_url())
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run the migrations inside one transaction."""
    logger.info("Running migrations online against %s", _safe_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    logger.info("Migrations complete")


def _safe_url() -> str:
    """Return the database host without the credentials, safe to log."""
    without_scheme = settings.database_url.split("://", 1)[-1]
    return without_scheme.rsplit("@", 1)[-1]


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
