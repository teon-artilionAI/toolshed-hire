"""The in memory reservation repository, and the read models it builds.

This is the booking half of the in memory unit of work in `memory`. It keeps
whole aggregates in the working copy of one transaction and hands the same
objects back, so a move a use case makes on a reservation is kept when the
transaction commits and thrown away when it does not.

It applies the scope of the caller the way the SQL repository does. A
reservation that belongs to somebody else is answered as though it did not
exist, so a use case can be tested for the refusal with no database.

It makes no attempt at locking. `find_for_update` and `lock_due_holds` return
what they find at once. The row locks are proved against PostgreSQL in
tests/integration.

A reservation here has no stored creation time, so its place in the list is
used for one. Each reservation is a second newer than the one before it,
which is all a test of the order of a list needs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from app.application.booking.read_models import (
    ReservationDetail,
    ReservationKey,
    ReservationLineDetail,
    ReservationPage,
    ReservationSearch,
)
from app.application.ownership import OwnerScope
from app.domain.booking import Reservation, ReservationLine, format_reference
from app.domain.enums import ReservationStatus

if TYPE_CHECKING:
    from tests.support.memory import MemoryStore, Records

# The creation time of the first reservation a store is given.
MEMORY_EPOCH: Final[datetime] = datetime(2026, 3, 1, 6, 0, tzinfo=UTC)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)


class MemoryReservations:
    """The reservation repository over the working copy of one transaction."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def add(self, reservation: Reservation) -> None:
        """Keep the reservation in the working copy."""
        self._working.reservations.append(reservation)

    def next_reference(self, year: int) -> str:
        """Return the next reference from the store's counter."""
        return format_reference(year, self._store.next_reference_number())

    def find_for_update(self, key: ReservationKey, scope: OwnerScope) -> Reservation | None:
        """Return the working copy of one reservation, if the scope lets the caller act on it."""
        return self._find(key, scope)

    def save(self, reservation: Reservation) -> None:
        """Keep a changed reservation in place of the one with the same key."""
        for index, existing in enumerate(self._working.reservations):
            if existing.id == reservation.id:
                self._working.reservations[index] = reservation
                return
        raise LookupError(
            f"Attempted to save reservation {reservation.reference}, which was never added."
        )

    def lock_due_holds(self, now: datetime, limit: int) -> list[Reservation]:
        """Return up to `limit` held reservations whose hold has run out, oldest first."""
        due = [
            reservation
            for reservation in self._working.reservations
            if reservation.status is ReservationStatus.HELD
            and reservation.hold_expires_at is not None
            and reservation.hold_expires_at < now
        ]
        due.sort(key=lambda reservation: (reservation.hold_expires_at, str(reservation.id)))
        return due[:limit]

    def find_detail(self, key: ReservationKey, scope: OwnerScope) -> ReservationDetail | None:
        """Return one reservation as a read model, if the scope lets the caller see it."""
        found = self._find(key, scope)
        return self._detail_of(found) if found is not None else None

    def search(self, search: ReservationSearch, scope: OwnerScope) -> ReservationPage:
        """Return one page of the reservations that match, newest first."""
        matching = [
            reservation
            for reservation in reversed(self._working.reservations)
            if self._is_within(reservation, scope) and _matches(reservation, search)
        ]
        page = matching[search.offset : search.offset + search.page_size]
        return ReservationPage(
            items=tuple(self._detail_of(reservation) for reservation in page),
            page=search.page,
            page_size=search.page_size,
            total=len(matching),
        )

    def _find(self, key: ReservationKey, scope: OwnerScope) -> Reservation | None:
        """Return the one reservation a key names, when the scope reaches it."""
        for reservation in self._working.reservations:
            named = (
                reservation.id == key.reservation_id
                if key.reservation_id is not None
                else reservation.reference == key.reference
            )
            if named and self._is_within(reservation, scope):
                return reservation
        return None

    def _is_within(self, reservation: Reservation, scope: OwnerScope) -> bool:
        """Return True when the scope lets the caller see this reservation."""
        if scope.customer_user_id is None:
            return True
        owner = self._store.profile_with_id(reservation.customer_profile_id)
        return owner is not None and owner.user_account_id == scope.customer_user_id

    def _detail_of(self, reservation: Reservation) -> ReservationDetail:
        """Build the read model of one reservation from the store's reference data."""
        branch = self._store.branches[reservation.branch_id]
        owner = self._store.profile_with_id(reservation.customer_profile_id)
        if owner is None:
            raise LookupError(
                f"Attempted to read reservation {reservation.reference}, whose customer "
                "profile is not in the store."
            )
        position = self._working.reservations.index(reservation)
        return ReservationDetail(
            id=reservation.id,
            reference=reservation.reference,
            status=reservation.status,
            branch_id=reservation.branch_id,
            branch_code=branch.code,
            branch_name=branch.name,
            start_date=reservation.period.start,
            end_date=reservation.period.end,
            lines=tuple(self._line_detail_of(line) for line in reservation.lines),
            subtotal_ex_vat=reservation.subtotal_ex_vat().amount,
            discount_percent=reservation.discount_percent(),
            vat_amount=reservation.vat_amount,
            estimated_total_inc_vat=reservation.estimated_total_inc_vat,
            deposit_total=reservation.deposit_total,
            hold_expires_at=reservation.hold_expires_at,
            confirmed_at=reservation.confirmed_at,
            cancelled_at=reservation.cancelled_at,
            cancellation_reason=reservation.cancellation_reason,
            customer_profile_id=reservation.customer_profile_id,
            customer_name=owner.display_name,
            customer_email_verified=owner.email_verified,
            created_at=MEMORY_EPOCH + position * ONE_SECOND,
        )

    def _line_detail_of(self, line: ReservationLine) -> ReservationLineDetail:
        """Build the read model of one line, with the tags of the units it holds."""
        model = self._store.product_models[line.product_model_id]
        tags = sorted(
            self._store.tag_of(allocation.asset_id) for allocation in line.active_allocations()
        )
        return ReservationLineDetail(
            model_slug=model.slug,
            model_name=model.name,
            quantity=line.quantity,
            daily_rate=line.daily_rate_snapshot,
            weekly_rate=line.weekly_rate_snapshot,
            deposit_per_unit=line.deposit_snapshot,
            line_subtotal_ex_vat=line.line_subtotal_ex_vat,
            allocated_count=len(tags),
            asset_tags=tuple(tags),
        )


def _matches(reservation: Reservation, search: ReservationSearch) -> bool:
    """Return True when a reservation passes the filters a list was narrowed with."""
    return (
        (search.status is None or reservation.status is search.status)
        and (
            search.customer_profile_id is None
            or reservation.customer_profile_id == search.customer_profile_id
        )
        and (search.branch_id is None or reservation.branch_id == search.branch_id)
    )


__all__ = ["MEMORY_EPOCH", "MemoryReservations"]
