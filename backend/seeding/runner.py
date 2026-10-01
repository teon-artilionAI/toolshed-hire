"""Run the whole load in one transaction.

`seed_database` does the work against a session somebody else owns, which is
what the tests call. `run_seed` is what the entry point calls. It opens the
session, commits once at the end and reports what happened, so a failure half
way leaves the database exactly as it was.
"""

from __future__ import annotations

import logging

from sqlmodel import Session

from app.config import settings
from app.infrastructure.database import session_scope
from seeding.accounts import load_accounts, load_customer_profiles, resolve_seed_password
from seeding.catalogue import load_branches, load_categories, load_product_models
from seeding.fleet import load_assets
from seeding.history import load_worked_example
from seeding.report import SeedTally
from seeding.sequences import advance_reference_sequences

logger = logging.getLogger("seed")


def seed_database(session: Session, password: str) -> SeedTally:
    """Load every seeded row that is missing, without committing.

    The order is the dependency order. Branches, categories and product models
    come first, then the units, then the people, then the closed hire that
    refers to all of them, and last the sequences.

    Args:
        session: An open session. The caller owns the commit.
        password: The plain password given to every account this run creates.

    Returns:
        What the run created and what it found already present.

    Raises:
        SeedDataError: If the seed data cannot be loaded as it is written.
        ValidationFailure: If the password breaks the password policy.

    """
    tally = SeedTally()
    branches = load_branches(session, tally)
    categories = load_categories(session, tally)
    models = load_product_models(session, categories, tally)
    load_assets(session, branches, models, tally)
    accounts = load_accounts(session, branches, password, tally)
    profiles = load_customer_profiles(session, branches, accounts, tally)
    load_worked_example(session, branches, models, accounts, profiles, tally)
    advance_reference_sequences(session, tally)
    return tally


def run_seed() -> SeedTally:
    """Seed the configured database in one transaction and log the outcome.

    Returns:
        What the run created and what it found already present.

    Raises:
        RuntimeError: If SEED_PASSWORD is unset outside development and test.
        SeedDataError: If the seed data cannot be loaded as it is written.

    """
    password = resolve_seed_password()
    logger.info("seed.started", extra={"environment": settings.environment.value})
    with session_scope() as session:
        tally = seed_database(session, password)
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
            "created_by_kind": tally.created,
            "found_by_kind": tally.found,
        },
    )
    return tally
