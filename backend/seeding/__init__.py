"""The loader behind `python seed.py`.

`seed_data` holds what to load and knows nothing about a database. This package
holds how to load it. I keep the two apart so the fleet can be reviewed as data
without reading a line of persistence code.

Every row is matched on its natural key, the branch code, the category code,
the SKU, the asset tag, the email address or the reference. A row that is
already there is left exactly as it is, so a second run changes nothing and a
run against a live database never overwrites what the counter has done since.

The modules follow the order of the load. `catalogue` writes the branches, the
categories and the product models. `fleet_plan` works out the tag of every
unit without touching the database, and `fleet` writes them. `people` lists
the accounts and `accounts` writes them. `worked_example` holds the fixed
figures of the one closed hire and `history` writes it. `sequences` moves the
reference sequences past the seeded numbers. `runner` runs all of it in one
transaction.
"""

from __future__ import annotations

from seeding.errors import SeedDataError
from seeding.report import SeedTally
from seeding.runner import run_seed, seed_database

__all__ = ["SeedDataError", "SeedTally", "run_seed", "seed_database"]
