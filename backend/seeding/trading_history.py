"""Write a season of closed hires, so the report has history to read.

The utilisation and gross contribution report (FR-24) reads closed hires,
their charges and their damage reports. Without history it shows nought for
every month, and which equipment earns its keep cannot be answered. This step
writes the hires of 1 June to 30 September 2026 at all three branches, every
one booked, collected, returned and settled through the domain the way the
counter does it.

The history is one unit. Its reservations, rentals and damage reports sit in
reserved reference ranges, and its walk in customers in a reserved phone
block. None of it there means all of it is written. All of it there means
nothing is written and the run says so. Anything between cannot come from this
loader, which writes it in the one transaction of the seed, so it is refused
instead of being patched up, the way the worked example is.

Every unit ends the season on the shelf and every report is resolved, so
today's fleet, the dashboard's live counts and the availability search are
exactly as they were. The units the history hires are the ones on the shelf
when it runs, and a unit is never put out on a day the database already has
it away. No audit event is written, because the application did none of this.

The rows are written in bulk by `trading_write`, in about twenty statements,
so the step costs a handful of round trips however far away the database is.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlmodel import Session

from seeding.errors import SeedDataError
from seeding.report import SeedTally
from seeding.trading_customers import PHONE_BLOCK, WALK_INS, WalkInProfile, walk_in_profiles
from seeding.trading_hire import FleetBook, HireCast, run_hire
from seeding.trading_people import AccountCustomer, PeopleRead, read_people
from seeding.trading_plan import plan_season
from seeding.trading_reads import (
    FleetRead,
    HistoryCounts,
    count_history,
    read_already_away,
    read_fleet,
)
from seeding.trading_records import (
    DAMAGE_RANGE,
    RENTAL_RANGE,
    RESERVATION_RANGE,
    CustomerChoice,
    PlannedHire,
)
from seeding.trading_rows import (
    HistoryRows,
    add_hire_rows,
    counts_of,
    customer_key,
    customer_row,
)
from seeding.trading_write import Timings, insert_history, log_created

logger = logging.getLogger("seed")

KIND_PREFIX: Final[str] = "trading_"
# The two customer accounts hire now and then, less often than any walk in.
ACCOUNT_CUSTOMER_WEIGHT: Final[int] = 1


@dataclass(frozen=True, slots=True)
class _Customer:
    """Who a customer key stands for when a hire is cast."""

    profile_id: UUID
    discount_percent: Decimal
    account_id: UUID | None


def load_trading_history(session: Session, tally: SeedTally) -> None:
    """Write the season of trading history unless it is already there.

    Args:
        session: An open session on a database the rest of the seed has
            loaded. The caller owns the commit.
        tally: Where the created and found counts are recorded.

    Raises:
        SeedDataError: If part of the history is there and part is not, the
            accounts and profiles it hires to are missing, or no unit is on
            the shelf to hire.

    """
    started = time.perf_counter()
    counts = count_history(session)
    if _history_present(counts):
        for kind, count in counts.by_kind().items():
            tally.record(f"{KIND_PREFIX}{kind}", created=0, found=count)
        logger.info(
            "seed.trading_history_found",
            extra={"outcome": "already present, nothing written", **counts.by_kind()},
        )
        return
    fleet = read_fleet(session)
    people = read_people(session)
    profiles = walk_in_profiles()
    plan = plan_season(
        fleet.units, read_already_away(session), _customer_choices(profiles, people)
    )
    if not plan:
        raise SeedDataError(
            "The trading history found no unit on the shelf to hire, so it would write its "
            "customers and no hire. Load the fleet before the history."
        )
    planned = time.perf_counter()
    rows = _rows_of(plan, profiles, fleet, people)
    run = time.perf_counter()
    statements = insert_history(session, rows)
    for kind, count in counts_of(rows):
        tally.record(f"{KIND_PREFIX}{kind}", created=count, found=0)
    log_created(plan, rows, statements, Timings(started, planned, run, time.perf_counter()))


def _history_present(counts: HistoryCounts) -> bool:
    """Return True when the whole history is there and False when none of it is.

    Raises:
        SeedDataError: If only part of it is there.

    """
    found = counts.by_kind()
    if not any(found.values()):
        return False
    whole = (
        counts.reservation > 0
        and counts.rental == counts.reservation
        and counts.customer_profile == len(WALK_INS)
    )
    if whole:
        return True
    raise SeedDataError(
        f"Found part of the trading history, {found}. The seed writes it whole in one "
        "transaction, so this database was changed by something else. Remove the rows in "
        f"the reserved ranges {RESERVATION_RANGE}, {RENTAL_RANGE} and {DAMAGE_RANGE} and "
        f"the walk in customers of the {PHONE_BLOCK} phone block, then run the seed again."
    )


def _customer_choices(
    profiles: Sequence[WalkInProfile], people: PeopleRead
) -> list[CustomerChoice]:
    """Return everybody the season may hire to, the walk ins and the two accounts."""
    choices = [
        CustomerChoice(profile.key, profile.branch_code, profile.weight, has_login=False)
        for profile in profiles
    ]
    choices.extend(
        CustomerChoice(
            account.email, account.branch_code, ACCOUNT_CUSTOMER_WEIGHT, has_login=True
        )
        for account in people.account_customers
    )
    return choices


def _rows_of(
    plan: Sequence[PlannedHire],
    profiles: Sequence[WalkInProfile],
    fleet: FleetRead,
    people: PeopleRead,
) -> HistoryRows:
    """Run every planned hire through the domain and return the rows it left behind."""
    rows = HistoryRows(
        customer_profiles=[
            customer_row(profile, fleet.branch_ids[profile.branch_code]) for profile in profiles
        ]
    )
    customers = _customers_by_key(profiles, people.account_customers)
    book = FleetBook(models=fleet.models, units=fleet.domain_units)
    for hire in plan:
        customer = customers[hire.customer_key]
        staff_id = people.staff_by_branch[hire.branch_code]
        online_by = customer.account_id if hire.booked_online else None
        cast = HireCast(
            branch_id=fleet.branch_ids[hire.branch_code],
            customer_profile_id=customer.profile_id,
            discount_percent=customer.discount_percent,
            booked_by=online_by if online_by is not None else staff_id,
            staff_id=staff_id,
        )
        add_hire_rows(rows, hire, run_hire(hire, cast, book))
    return rows


def _customers_by_key(
    profiles: Sequence[WalkInProfile], accounts: Sequence[AccountCustomer]
) -> Mapping[str, _Customer]:
    """Return who each customer key stands for, walk ins by phone and accounts by email."""
    customers = {
        profile.key: _Customer(customer_key(profile), profile.trade_discount_percent, None)
        for profile in profiles
    }
    for account in accounts:
        customers[account.email] = _Customer(
            account.profile_id, account.discount_percent, account.account_id
        )
    return customers
