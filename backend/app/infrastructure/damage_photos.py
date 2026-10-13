"""The SQL repository of damage photographs, which is the `damage_photo` table of revision 0014.

The row says where a photograph is stored and who attached it. The photograph
itself is in the bucket. A row is inserted once and never changed, and the
application role may do nothing else to the table.

Attaching a photograph locks the report's row with `SELECT ... FOR UPDATE`
and counts its photographs in the next statement. Under READ COMMITTED that
count sees whatever the transaction that held the lock before committed, so
two photographs sent at once for one report are counted in turn.

Every read takes one statement. The photographs of a report are reached
through `ix_damage_photo_report`. The photographs of a hire go from the rental
to its items, to the reports that name them through
`ix_damage_report_rental_item`, and to their photographs through the same index.
A customer's read carries the customer in the WHERE clause, joined from the
rental through the reservation to the profile (BR-42), so a hire that is not
theirs finds nothing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, Select, UnaryExpression, func
from sqlalchemy import select as select_columns
from sqlmodel import Session, col

from app.application.hire.damage_models import DamageReportKey
from app.application.hire.damage_photo_models import DamagePhotoView, PhotoTarget
from app.application.ownership import OwnerScope
from app.domain.damage_photo import DamagePhoto as DomainPhoto
from app.domain.damage_photo import PhotoFormat
from app.infrastructure.booking_mapping import required_utc
from app.infrastructure.damage_report_query import report_key_condition
from app.infrastructure.models import (
    Asset,
    CustomerProfile,
    DamagePhoto,
    DamageReport,
    Rental,
    RentalItem,
    Reservation,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

UPLOADED_AT_COLUMN: Final[str] = "damage_photo.uploaded_at"
FORMAT_OF_CONTENT_TYPE: Final[dict[str, PhotoFormat]] = {
    photo_format.content_type: photo_format for photo_format in PhotoFormat
}


class SqlDamagePhotoRepository:
    """Reads and writes the records of damage photographs through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def target_of(self, key: DamageReportKey) -> PhotoTarget | None:
        """Return the report a photograph would be attached to, or None when there is none."""
        row = self._session.execute(_targets().where(report_key_condition(key))).mappings().first()
        return None if row is None else _target_of(row)

    def lock_target(self, report_id: UUID) -> PhotoTarget | None:
        """Lock the report's row, then return it with the photographs it holds now."""
        locked = self._session.execute(
            select_columns(col(DamageReport.id))
            .where(col(DamageReport.id) == report_id)
            .with_for_update(of=DamageReport)
        ).first()
        logger.debug(
            "damage_photo.report_locked",
            extra={"damage_report_id": str(report_id), "found": locked is not None},
        )
        if locked is None:
            return None
        row = (
            self._session.execute(_targets().where(col(DamageReport.id) == report_id))
            .mappings()
            .first()
        )
        return None if row is None else _target_of(row)

    def add(self, photo: DomainPhoto) -> None:
        """Write the record of a stored photograph, flushed so it can be read back."""
        self._session.add(
            DamagePhoto(
                id=photo.id,
                damage_report_id=photo.damage_report_id,
                object_key=photo.object_key,
                content_type=photo.photo_format.content_type,
                size_bytes=photo.size_bytes,
                uploaded_by_user_id=photo.uploaded_by_user_id,
                uploaded_at=photo.uploaded_at,
            )
        )
        self._session.flush()
        logger.debug(
            "damage_photo.inserted",
            extra={
                "damage_photo_id": str(photo.id),
                "damage_report_id": str(photo.damage_report_id),
            },
        )

    def report_id_of(self, key: DamageReportKey) -> UUID | None:
        """Return the key of the report named by its key or reference, or None."""
        found: UUID | None = self._session.execute(
            select_columns(col(DamageReport.id)).where(report_key_condition(key))
        ).scalar_one_or_none()
        return found

    def of_report(self, report_id: UUID) -> tuple[DamagePhotoView, ...]:
        """Return the photographs of one report, in the order they were attached."""
        with logged_query(
            logger, "damage_photo.report_list", {"damage_report_id": str(report_id)}
        ) as outcome:
            rows = (
                self._session.execute(
                    _photos()
                    .where(col(DamagePhoto.damage_report_id) == report_id)
                    .order_by(*_oldest_first())
                )
                .mappings()
                .all()
            )
            outcome.row_count = len(rows)
        return tuple(_view_of(row) for row in rows)

    def find_on_report(self, report_id: UUID, photo_id: UUID) -> DamagePhotoView | None:
        """Return one photograph of one report, or None when the report has no such photograph."""
        row = (
            self._session.execute(
                _photos().where(
                    col(DamagePhoto.damage_report_id) == report_id, col(DamagePhoto.id) == photo_id
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _view_of(row)

    def rental_is_visible(self, rental_id: UUID, scope: OwnerScope) -> bool:
        """Return True when the rental exists and the scope may read it."""
        statement = (
            select_columns(col(Rental.id))
            .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
            .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
            .where(col(Rental.id) == rental_id, *_scope_conditions(scope))
        )
        return self._session.execute(statement).first() is not None

    def of_rental(self, rental_id: UUID, scope: OwnerScope) -> tuple[DamagePhotoView, ...]:
        """Return the photographs of every report on one rental, oldest first."""
        filters = {"rental_id": str(rental_id), "scoped": scope.is_restricted}
        with logged_query(logger, "damage_photo.rental_list", filters) as outcome:
            rows = (
                self._session.execute(
                    _on_rental(rental_id, scope).order_by(*_oldest_first())
                )
                .mappings()
                .all()
            )
            outcome.row_count = len(rows)
        return tuple(_view_of(row) for row in rows)

    def find_on_rental(
        self, rental_id: UUID, photo_id: UUID, scope: OwnerScope
    ) -> DamagePhotoView | None:
        """Return one photograph of a report on the rental, or None when the scope finds none."""
        row = (
            self._session.execute(
                _on_rental(rental_id, scope).where(col(DamagePhoto.id) == photo_id)
            )
            .mappings()
            .first()
        )
        return None if row is None else _view_of(row)


def _targets() -> Select[tuple[object, ...]]:
    """Return the statement that reads a report with its branch and its photograph count."""
    photos_held = (
        select_columns(func.count())
        .select_from(DamagePhoto)
        .where(col(DamagePhoto.damage_report_id) == col(DamageReport.id))
        .correlate(DamageReport)
        .scalar_subquery()
    )
    return (
        select_columns(
            col(DamageReport.id).label("report_id"),
            col(DamageReport.reference).label("reference"),
            col(Asset.branch_id).label("branch_id"),
            photos_held.label("photos_held"),
        )
        .select_from(DamageReport)
        .join(Asset, col(Asset.id) == col(DamageReport.asset_id))
    )


def _photos() -> Select[tuple[object, ...]]:
    """Return the statement that reads photographs with the reference of their report."""
    columns: list[ColumnElement[object]] = [
        col(DamagePhoto.id).label("id"),
        col(DamagePhoto.damage_report_id).label("damage_report_id"),
        col(DamageReport.reference).label("damage_report_reference"),
        col(DamagePhoto.object_key).label("object_key"),
        col(DamagePhoto.content_type).label("content_type"),
        col(DamagePhoto.size_bytes).label("size_bytes"),
        col(DamagePhoto.uploaded_at).label("uploaded_at"),
    ]
    return (
        select_columns(*columns)
        .select_from(DamagePhoto)
        .join(DamageReport, col(DamageReport.id) == col(DamagePhoto.damage_report_id))
    )


def _on_rental(rental_id: UUID, scope: OwnerScope) -> Select[tuple[object, ...]]:
    """Return the photographs of every report filed against an item of one rental."""
    return (
        _photos()
        .join(RentalItem, col(RentalItem.id) == col(DamageReport.rental_item_id))
        .join(Rental, col(Rental.id) == col(RentalItem.rental_id))
        .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
        .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
        .where(col(Rental.id) == rental_id, *_scope_conditions(scope))
    )


def _oldest_first() -> tuple[UnaryExpression[datetime], UnaryExpression[UUID]]:
    """Return the order photographs are listed in, oldest first with a tie broken by key."""
    return (col(DamagePhoto.uploaded_at).asc(), col(DamagePhoto.id).asc())


def _scope_conditions(scope: OwnerScope) -> list[ColumnElement[bool]]:
    """Return the condition that limits a read to one customer's hires."""
    if scope.customer_user_id is None:
        return []
    return [col(CustomerProfile.user_account_id) == scope.customer_user_id]


def _target_of(row: RowMapping) -> PhotoTarget:
    """Return what attaching a photograph needs to know, from a row of `_targets`."""
    return PhotoTarget(
        report_id=row["report_id"],
        reference=row["reference"],
        branch_id=row["branch_id"],
        photos_held=int(row["photos_held"]),
    )


def _view_of(row: RowMapping) -> DamagePhotoView:
    """Return one photograph as a read model, from a row of `_photos`.

    Raises:
        ValueError: If the stored media type is not one a photograph is stored
            as. The service writes nothing else, so this is a row written by hand.

    """
    content_type = row["content_type"]
    photo_format = FORMAT_OF_CONTENT_TYPE.get(content_type)
    if photo_format is None:
        raise ValueError(
            f"Attempted to read damage photograph {row['id']}, stored as {content_type!r}, "
            f"which is not one of {sorted(FORMAT_OF_CONTENT_TYPE)}."
        )
    return DamagePhotoView(
        id=row["id"],
        damage_report_id=row["damage_report_id"],
        damage_report_reference=row["damage_report_reference"],
        object_key=row["object_key"],
        photo_format=photo_format,
        size_bytes=int(row["size_bytes"]),
        uploaded_at=required_utc(row["uploaded_at"], UPLOADED_AT_COLUMN),
    )
