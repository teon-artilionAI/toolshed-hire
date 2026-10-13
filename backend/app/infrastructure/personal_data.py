"""The SQL side of anonymising a customer, on the session of its unit of work (#113).

The profile and the account are written over column by column, with the
values the domain gives, and `PROFILE_COLUMNS` and `ACCOUNT_COLUMNS` name the
columns. A unit test holds both against the personal data map, so a column the
map names as identifying and this module forgets fails the build.

The free text columns the map lists on the customer's own rows are each given
one treatment in `FREE_TEXT_TREATMENT`, and the same test fails when the map
lists one that has none. What someone typed is cleared where the column may be
null and replaced with `REMOVED_NOTE` where it may not. Text the system wrote
from references and amounts says nothing about a person and is kept, because it
is part of a financial record. `audit_event` is left out on purpose. The
application role may only add to it (BR-49).

Every write is one UPDATE for each table, keyed on the customer through the
indexes the reads of a customer's bookings and hires already use, so an
anonymisation costs a handful of statements whatever the customer hired.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from typing import Final
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    ScalarSelect,
    Update,
    case,
    func,
    literal,
    select,
    update,
)
from sqlalchemy.orm import Mapped
from sqlalchemy.sql import Select
from sqlmodel import Session, col

from app.application.identity.anonymisation_ports import ErasedRows, ErasureSubject
from app.domain.anonymisation import (
    OPEN_BOOKING_STATUSES,
    REMOVED_NOTE,
    AnonymisedAccount,
    AnonymisedProfile,
    OpenMatters,
    anonymised_email,
)
from app.domain.enums import ChargeStatus, RentalStatus
from app.infrastructure.dormant_customers import dormant_customers_statement
from app.infrastructure.models import (
    Charge,
    CustomerProfile,
    DamageReport,
    Notification,
    RefreshSession,
    Rental,
    RentalItem,
    Reservation,
    UserAccount,
)

logger = logging.getLogger(__name__)

NOTHING_OWED: Final[int] = 0


class Treatment(str, Enum):
    """What an anonymisation does to one free text column."""

    CLEARED = "cleared"
    REPLACED = "replaced"
    KEPT = "kept"


# The identifying columns of the profile, which are the fields of the domain's
# values, and of the account, which also loses its phone.
PROFILE_COLUMNS: Final[tuple[str, ...]] = tuple(AnonymisedProfile.__dataclass_fields__)
ACCOUNT_COLUMNS: Final[tuple[str, ...]] = tuple(AnonymisedAccount.__dataclass_fields__)
# The browser and the address a refresh session recorded are cleared.
SESSION_COLUMNS: Final[tuple[str, ...]] = ("user_agent", "ip_address")

# Every free text column the personal data map lists on a customer's own rows,
# but the audit trail's, and what an anonymisation does to it.
FREE_TEXT_TREATMENT: Final[dict[tuple[str, str], Treatment]] = {
    ("reservation", "notes"): Treatment.CLEARED,
    ("reservation", "cancellation_reason"): Treatment.REPLACED,
    ("rental_item", "notes"): Treatment.CLEARED,
    ("damage_report", "description"): Treatment.REPLACED,
    ("damage_report", "resolution_notes"): Treatment.CLEARED,
    # Written by the system from the hire's references and amounts. They are
    # the lines of a financial record and name nobody.
    ("charge", "description"): Treatment.KEPT,
    ("charge", "payment_reference"): Treatment.KEPT,
    # Typed by the owner when a charge is waived. The audit event of the
    # waiver keeps it, and the row must still say something (BR-25).
    ("charge", "waiver_reason"): Treatment.REPLACED,
    # Written by the system from the booking's reference.
    ("notification", "subject"): Treatment.KEPT,
    # A provider's error can quote the address it could not deliver to.
    ("notification", "last_error"): Treatment.CLEARED,
}


class SqlPersonalDataEraser:
    """Reads a customer for an anonymisation and writes over their rows, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the eraser to the session of its unit of work."""
        self._session = session

    def subject_for_update(self, customer_profile_id: UUID) -> ErasureSubject | None:
        """Return the customer, with the profile and then the account locked, or None."""
        profile = self._session.execute(
            select(
                col(CustomerProfile.user_account_id),
                col(CustomerProfile.customer_type),
                col(CustomerProfile.anonymised_at),
            )
            .where(col(CustomerProfile.id) == customer_profile_id)
            .with_for_update()
        ).first()
        if profile is None:
            return None
        user_account_id, customer_type, anonymised_at = profile
        last_signed_in_at: datetime | None = None
        if user_account_id is not None:
            last_signed_in_at = self._session.execute(
                select(
                    func.coalesce(col(UserAccount.last_login_at), col(UserAccount.created_at))
                )
                .where(col(UserAccount.id) == user_account_id)
                .with_for_update()
            ).scalar_one()
        return ErasureSubject(
            customer_profile_id=customer_profile_id,
            user_account_id=user_account_id,
            customer_type=customer_type,
            anonymised_at=anonymised_at,
            last_signed_in_at=last_signed_in_at,
        )

    def open_matters(self, customer_profile_id: UUID) -> OpenMatters:
        """Return the bookings, hires and money the customer still has open, in one statement."""
        charge_pending = (
            select(col(Charge.id))
            .where(
                col(Charge.rental_id) == col(Rental.id),
                col(Charge.status) == ChargeStatus.PENDING,
            )
            .exists()
        )
        bookings = (
            select(func.count())
            .select_from(Reservation)
            .where(
                col(Reservation.customer_profile_id) == customer_profile_id,
                col(Reservation.status).in_(OPEN_BOOKING_STATUSES),
            )
            .scalar_subquery()
        )
        unsettled = _count_hires(customer_profile_id, col(Rental.status) != RentalStatus.SETTLED)
        owing = _count_hires(
            customer_profile_id, (col(Rental.balance_due) > NOTHING_OWED) | charge_pending
        )
        open_bookings, unsettled_hires, hires_owing = self._session.execute(
            select(bookings, unsettled, owing)
        ).one()
        matters = OpenMatters(
            open_bookings=int(open_bookings),
            unsettled_hires=int(unsettled_hires),
            hires_owing=int(hires_owing),
        )
        logger.debug(
            "identity.open_matters_read",
            extra={"customer_profile_id": str(customer_profile_id), **asdict(matters)},
        )
        return matters

    def erase(
        self,
        subject: ErasureSubject,
        *,
        profile: AnonymisedProfile,
        account: AnonymisedAccount | None,
        at: datetime,
    ) -> ErasedRows:
        """Write the anonymised values over the customer's rows and stamp the profile."""
        profile_id = subject.customer_profile_id
        self._session.execute(
            update(CustomerProfile)
            .where(col(CustomerProfile.id) == profile_id)
            .values(**asdict(profile), anonymised_at=at)
        )
        sessions = 0
        if subject.user_account_id is not None and account is not None:
            sessions = self._erase_account(subject.user_account_id, account)
        bookings_of_customer = select(col(Reservation.id)).where(
            col(Reservation.customer_profile_id) == profile_id
        )
        hires_of_customer = _hires_of(profile_id)
        items_of_customer = select(col(RentalItem.id)).where(
            col(RentalItem.rental_id).in_(hires_of_customer)
        )
        erased = ErasedRows(
            sessions=sessions,
            bookings=self._rowcount(
                update(Reservation)
                .where(col(Reservation.customer_profile_id) == profile_id)
                .values(
                    notes=None,
                    cancellation_reason=_replaced_when_written(
                        col(Reservation.cancellation_reason)
                    ),
                )
            ),
            hire_items=self._rowcount(
                update(RentalItem)
                .where(col(RentalItem.rental_id).in_(hires_of_customer))
                .values(notes=None)
            ),
            damage_reports=self._rowcount(
                update(DamageReport)
                .where(col(DamageReport.rental_item_id).in_(items_of_customer))
                .values(description=REMOVED_NOTE, resolution_notes=None)
            ),
            charges=self._rowcount(
                update(Charge)
                .where(
                    col(Charge.rental_id).in_(hires_of_customer),
                    col(Charge.waiver_reason).is_not(None),
                )
                .values(waiver_reason=REMOVED_NOTE)
            ),
            notifications=self._rowcount(
                update(Notification)
                .where(col(Notification.reservation_id).in_(bookings_of_customer))
                .values(recipient_email=anonymised_email(profile_id), last_error=None)
            ),
        )
        logger.info(
            "identity.customer_erased",
            extra={"customer_profile_id": str(profile_id), **asdict(erased)},
        )
        return erased

    def dormant_customers(
        self, cutoff: datetime, *, after: UUID | None, limit: int
    ) -> tuple[UUID, ...]:
        """Return the next customers the monthly job may anonymise, in the order of their key."""
        filters = {
            "cutoff": cutoff.isoformat(),
            "after": str(after) if after is not None else None,
            "limit": limit,
        }
        logger.debug("identity.dormant_customers_started", extra=filters)
        found = tuple(
            self._session.execute(dormant_customers_statement(cutoff, after=after, limit=limit))
            .scalars()
            .all()
        )
        logger.info("identity.dormant_customers_read", extra={**filters, "row_count": len(found)})
        return found

    def _erase_account(self, user_account_id: UUID, account: AnonymisedAccount) -> int:
        """Write over the account, stop it signing in, and clear its sessions' browser and address.

        Returns:
            How many refresh sessions were cleared.

        """
        self._session.execute(
            update(UserAccount)
            .where(col(UserAccount.id) == user_account_id)
            .values(
                **asdict(account),
                is_active=False,
                email_verification_token_hash=None,
                email_verification_expires_at=None,
                password_reset_token_hash=None,
                password_reset_expires_at=None,
            )
        )
        return self._rowcount(
            update(RefreshSession)
            .where(col(RefreshSession.user_account_id) == user_account_id)
            .values(dict.fromkeys(SESSION_COLUMNS))
        )

    def _rowcount(self, statement: Update) -> int:
        """Run one UPDATE and return how many rows it wrote."""
        result = self._session.execute(statement)
        return result.rowcount if isinstance(result, CursorResult) else 0


def _hires_of(customer_profile_id: UUID) -> Select[tuple[UUID]]:
    """Return the hires of one customer, which are theirs through the booking each came from."""
    return (
        select(col(Rental.id))
        .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
        .where(col(Reservation.customer_profile_id) == customer_profile_id)
    )


def _count_hires(customer_profile_id: UUID, condition: ColumnElement[bool]) -> ScalarSelect[int]:
    """Return how many hires of one customer meet a condition, as a value of a statement."""
    return (
        select(func.count())
        .select_from(Rental)
        .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
        .where(col(Reservation.customer_profile_id) == customer_profile_id, condition)
        .scalar_subquery()
    )


def _replaced_when_written(column: Mapped[str | None]) -> ColumnElement[str | None]:
    """Return the note in place of a column's value, and null where there was none."""
    return case((column.is_(None), None), else_=literal(REMOVED_NOTE))
