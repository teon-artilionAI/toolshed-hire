"""Seed a database with the Toolshed Hire catalogue, fleet, people and closed hires.

The closed hires are the worked example of the design document and a season
of trading history from June to September 2026, which gives the utilisation
report something to read.

Run it from this directory as `python seed.py`, after `alembic upgrade head`.
It is safe to run as often as you like. Every row is matched on its natural
key and a row that is already there is left untouched, so a second run changes
nothing and says so.

This file is only the entry point. The data is in the `seed_data` package and
the loading is in the `seeding` package.

Passwords come from the SEED_PASSWORD environment variable. Outside development
and test the script refuses to run without it, because seeding a known password
into a reachable database is a hole nobody notices. When SEED_CUSTOMER_PASSWORD
is also set, the customer accounts get that one instead, so a customer login
can be handed out without giving away the staff and admin logins.
"""

from __future__ import annotations

import logging
import sys

from app.logging_config import configure_logging
from seeding import run_seed

logger = logging.getLogger("seed")

EXIT_FAILURE = 1


def main() -> int:
    """Configure logging, run the seed and return the process exit code."""
    configure_logging()
    try:
        run_seed()
    except Exception as exc:  # noqa: BLE001  the entry point reports and exits
        logger.exception("seed.failed", extra={"error_type": type(exc).__name__})
        return EXIT_FAILURE
    return 0


if __name__ == "__main__":
    sys.exit(main())
