"""Run the whole load in one transaction.

`seed_database` does the work against a session somebody else owns, which is
what the tests call. `run_seed` is what the entry point calls. It opens the
session, commits once at the end and reports what happened, so a failure half
way leaves the database exactly as it was.

`run_seed` writes the season of trading history after everything else, in the
same transaction. It is a step of its own and not part of `seed_database`, so
a test of the catalogue, the people and the worked example reads a database
that holds exactly those, and a test of the history asks for it by name.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from app.config import settings
from app.infrastructure.database import session_scope
from seeding.accounts import (
    correct_opening_dates,
    load_accounts,
    load_customer_profiles,
    resolve_customer_seed_password,
    resolve_seed_password,
)
from seeding.catalogue import load_branches, load_categories, load_product_models
from seeding.fleet import load_assets
from seeding.history import load_worked_example
from seeding.report import SeedTally
from seeding.sequences import advance_reference_sequences
from seeding.trading_history import load_trading_history

logger = logging.getLogger("seed")


def seed_database(
    session: Session, password: str, customer_password: str | None = None
) -> SeedTally:
    """Load every seeded row that is missing, without committing.

    The order is the dependency order. Branches, categories and product models
    come first, then the units, then the people with their opening dates put
    right, then the closed hire that refers to all of them, and last the
    sequences.

    Args:
        session: An open session. The caller owns the commit.
        password: The plain password given to the staff and admin accounts this
            run creates, and to the customers too when no separate customer
            password is given.
        customer_password: The plain password for the customer accounts this
            run creates, when it is to differ from the staff password.

    Returns:
        What the run created and what it found already present.

    Raises:
        SeedDataError: If the seed data cannot be loaded as it is written.
        ValidationFailure: If a password breaks the password policy.

    """
    tally = SeedTally()
    branches = load_branches(session, tally)
    categories = load_categories(session, tally)
    models = load_product_models(session, categories, tally)
    load_assets(session, branches, models, tally)
    accounts = load_accounts(session, branches, password, tally, customer_password)
    profiles = load_customer_profiles(session, branches, accounts, tally)
    correct_opening_dates(session, accounts, profiles, tally)
    load_worked_example(session, branches, models, accounts, profiles, tally)
    advance_reference_sequences(session, tally)
    return tally


def run_seed() -> SeedTally:
    """Seed the configured database and its trading history in one transaction and log it.

    Returns:
        What the run created and what it found already present.

    Raises:
        RuntimeError: If SEED_PASSWORD is unset outside development and test.
        SeedDataError: If the seed data cannot be loaded as it is written, or
            only part of the trading history is in the database.

    """
    password = resolve_seed_password()
    customer_password = resolve_customer_seed_password()
    logger.info(
        "seed.started",
        extra={
            "environment": settings.environment.value,
            "separate_customer_password": customer_password is not None,
        },
    )
    with session_scope() as session:
        tally = seed_database(session, password, customer_password)
        load_trading_history(session, tally)
    if tally.changed_nothing:
        logger.info(
            "seed.nothing_to_do",
            extra={
                "outcome": "every seeded row was already present, nothing was changed",
                "found_count": tally.total_found,
            },
        )
    logger.info(
        "seed.completed",
        extra={
            "created_count": tally.total_created,
            "found_count": tally.total_found,
            "corrected_count": tally.total_corrected,
            "created_by_kind": tally.created,
            "found_by_kind": tally.found,
            "corrected_by_kind": tally.corrected,
        },
    )
    return tally
