"""The statement that finds the customers the monthly anonymisation may take (#113).

A customer qualifies when nothing says they are still about.

- Their profile is not anonymised and was made before the cutoff.
- They have no account, or the account has not signed in since the cutoff. An
  account that never signed in counts from the day it was opened.
- No booking of theirs is open, and none was made since the cutoff, whatever
  became of it. A walk-in who booked last month and cancelled is still a
  customer of the branch.
- Every hire of theirs is settled, owes nothing, has no charge pending, and
  was settled, or brought back when it has no settlement, before the cutoff.

The statement reads a page of keys after the last key of the page before, in
key order. It walks `ix_customer_profile_identified` of revision 0015, which
holds the profiles not anonymised, so the profiles anonymised in earlier runs
are never read again. Each profile it passes is then tested with three probes,
the account by its key, the bookings through `ix_reservation_customer_start`
and the hires through the unique key on `rental.reservation_id`, with the
charges of a hire through `ix_charge_rental`. The work of a page is therefore
the profiles it walks past and not the size of any other table.

What still grows is the walk itself. A customer who hires every month stays a
profile the job walks past every month, because the probes are what tell them
apart from a dormant one. At a hundred times today's customers that is still
one pass over an index of keys once a month. If it ever matters, the way out
is a column holding each customer's last activity, kept by the booking, the
hire and the sign in, and an index on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.sql import Select
from sqlmodel import col

from app.domain.anonymisation import OPEN_BOOKING_STATUSES
from app.domain.enums import ChargeStatus, RentalStatus
from app.infrastructure.models import Charge, CustomerProfile, Rental, Reservation, UserAccount

NOTHING_OWED: Final[int] = 0


def dormant_customers_statement(
    cutoff: datetime, *, after: UUID | None, limit: int
) -> Select[tuple[UUID]]:
    """Return the statement that reads the next page of dormant customers' keys.

    Args:
        cutoff: Two years before the run.
        after: The last key of the page before, or None for the first page.
        limit: The most keys to read.

    """
    profile_id = col(CustomerProfile.id)
    conditions: list[ColumnElement[bool]] = [
        col(CustomerProfile.anonymised_at).is_(None),
        col(CustomerProfile.created_at) < cutoff,
        or_(
            col(UserAccount.id).is_(None),
            func.coalesce(col(UserAccount.last_login_at), col(UserAccount.created_at)) < cutoff,
        ),
        ~_booking_still_about(cutoff),
        ~_hire_still_about(cutoff),
    ]
    if after is not None:
        conditions.append(profile_id > after)
    return (
        select(profile_id)
        .outerjoin(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
        .where(*conditions)
        .order_by(profile_id)
        .limit(limit)
    )


def _booking_still_about(cutoff: datetime) -> ColumnElement[bool]:
    """Return whether the customer has a booking that is open or was made since the cutoff."""
    return exists().where(
        col(Reservation.customer_profile_id) == col(CustomerProfile.id),
        or_(
            col(Reservation.status).in_(OPEN_BOOKING_STATUSES),
            col(Reservation.created_at) >= cutoff,
        ),
    )


def _hire_still_about(cutoff: datetime) -> ColumnElement[bool]:
    """Return whether the customer has a hire still open, owing or ended since the cutoff."""
    charge_pending = exists().where(
        col(Charge.rental_id) == col(Rental.id),
        col(Charge.status) == ChargeStatus.PENDING,
    )
    ended_at = func.coalesce(col(Rental.settled_at), col(Rental.returned_at))
    return exists().where(
        col(Rental.reservation_id) == col(Reservation.id),
        col(Reservation.customer_profile_id) == col(CustomerProfile.id),
        or_(
            col(Rental.status) != RentalStatus.SETTLED,
            col(Rental.balance_due) > NOTHING_OWED,
            charge_pending,
            and_(ended_at.is_not(None), ended_at >= cutoff),
        ),
    )
