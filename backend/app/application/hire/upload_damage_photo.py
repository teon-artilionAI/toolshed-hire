"""The use case that attaches a photograph to a damage report (#83, C-29 to C-31).

Counter staff of the branch that holds the unit attach photographs, and an
administrator may at any branch, as with the report itself (BR-43). The work
runs in three steps, so neither the database nor the bucket waits on the other.

First the cheap refusals, before anything is decoded. The format is read from
the first bytes, and the report is read to check the branch and how many
photographs it holds. Then the photograph is re-encoded, which drops its
metadata, and stored under a random name. Last, in one unit of work, the report
is locked, counted again, and the record and its audit event are written.

The second count is the one that holds. Two photographs sent at once for one
report both pass the first, and the lock makes the second of them wait and see
the first. When that refuses a photograph it has already been stored, and the
object is left in the bucket with a warning in the log, because the service
account may create objects and never delete them. The lifecycle rule removes
it with the rest at the end of the retention period. The same is true of a
commit that fails after the upload. Both are rare, and holding a row lock for
the length of an upload to avoid them would be the worse trade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import uuid4

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.hire.damage_audit import DAMAGE_REPORT_ENTITY_TYPE
from app.application.hire.damage_models import DamageReportKey
from app.application.hire.damage_photo_models import DamagePhotoView, PhotoTarget
from app.application.hire.damage_photo_ports import PhotoCleaner, PhotoStore
from app.application.hire.damage_reads import REPORT_NOT_FOUND_MESSAGE
from app.application.unit_of_work import UnitOfWork
from app.domain.damage_photo import (
    DamagePhoto,
    ensure_photo_size,
    ensure_room_for_another_photo,
    photo_format_of,
    photo_object_key,
)
from app.domain.errors import NotFound, PhotoLimitReached
from app.domain.identity import Actor, ensure_branch_scope

logger = logging.getLogger(__name__)

PHOTO_ADDED_ACTION: Final[str] = "damage_report.photo_added"


@dataclass(frozen=True, slots=True)
class UploadDamagePhotoCommand:
    """A request to attach one photograph to a damage report.

    Attributes:
        actor: The member of staff attaching it.
        key: The report, by its key or its reference.
        content: The photograph exactly as it arrived.

    """

    actor: Actor
    key: DamageReportKey
    content: bytes


class UploadDamagePhotoUseCase:
    """Check, clean, store and record one damage photograph."""

    def __init__(
        self, uow: UnitOfWork, clock: Clock, store: PhotoStore, cleaner: PhotoCleaner
    ) -> None:
        """Keep the unit of work, the clock, the bucket and the re-encoder it runs with."""
        self._uow = uow
        self._clock = clock
        self._store = store
        self._cleaner = cleaner

    def execute(self, command: UploadDamagePhotoCommand) -> DamagePhotoView:
        """Attach the photograph, or refuse and keep nothing.

        Raises:
            PhotoTooLarge: If it is larger than 4 MB.
            UnsupportedPhoto: If its first bytes are not those of a JPEG or a PNG.
            NotFound: If there is no such report.
            BranchScopeError: If counter staff attach it at another branch.
            PhotoLimitReached: If the report holds six photographs already.
            ValidationFailure: If it cannot be decoded, or holds too many pixels.
            FeatureSwitchedOff: If no bucket is configured.

        """
        actor = command.actor
        logger.info(
            "damage_photo.upload_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "damage_report": str(command.key),
                "size_bytes": len(command.content),
            },
        )
        ensure_photo_size(len(command.content))
        photo_format = photo_format_of(command.content)
        target = self._checked_target(actor, command.key)
        cleaned = self._cleaner.reencode(command.content, photo_format)
        photo_id = uuid4()
        photo = DamagePhoto(
            id=photo_id,
            damage_report_id=target.report_id,
            object_key=photo_object_key(target.report_id, photo_id, photo_format),
            photo_format=photo_format,
            size_bytes=len(cleaned),
            uploaded_by_user_id=actor.user_id,
            uploaded_at=self._clock.now(),
        )
        self._store.put(photo.object_key, cleaned, photo_format.content_type)
        view = self._record(actor, photo)
        logger.info(
            "damage_photo.uploaded",
            extra={
                "damage_report_reference": view.damage_report_reference,
                "damage_photo_id": str(view.id),
                "photo_format": photo_format.value,
                "received_bytes": len(command.content),
                "stored_bytes": view.size_bytes,
            },
        )
        return view

    def _checked_target(self, actor: Actor, key: DamageReportKey) -> PhotoTarget:
        """Return the report, refusing before anything is decoded or stored.

        Raises:
            NotFound: If there is no such report.
            BranchScopeError: If counter staff reach for another branch.
            PhotoLimitReached: If the report is full already.

        """
        with self._uow as uow:
            target = uow.damage_photos.target_of(key)
        if target is None:
            logger.info("damage_photo.report_not_found", extra={"damage_report": str(key)})
            raise NotFound(REPORT_NOT_FOUND_MESSAGE, {"damage_report": str(key)})
        ensure_branch_scope(actor, target.branch_id)
        ensure_room_for_another_photo(target.photos_held)
        return target

    def _record(self, actor: Actor, photo: DamagePhoto) -> DamagePhotoView:
        """Count again under the report's lock, then write the record and its audit event.

        Raises:
            NotFound: If the report has gone, which nothing in the service does.
            PhotoLimitReached: If another photograph filled the report meanwhile.

        """
        with self._uow as uow:
            target = uow.damage_photos.lock_target(photo.damage_report_id)
            if target is None:
                self._left_in_bucket(photo, "the report could not be read again")
                raise NotFound(
                    REPORT_NOT_FOUND_MESSAGE, {"damage_report": str(photo.damage_report_id)}
                )
            try:
                ensure_room_for_another_photo(target.photos_held)
            except PhotoLimitReached:
                self._left_in_bucket(photo, "another photograph filled the report first")
                raise
            uow.damage_photos.add(photo)
            uow.audit.record(
                audit_event_for(
                    actor=actor,
                    entity_type=DAMAGE_REPORT_ENTITY_TYPE,
                    entity_id=target.report_id,
                    action=PHOTO_ADDED_ACTION,
                    occurred_at=photo.uploaded_at,
                    before_state={"photo_count": target.photos_held},
                    after_state={
                        "reference": target.reference,
                        "photo_count": target.photos_held + 1,
                        "damage_photo_id": str(photo.id),
                        "content_type": photo.photo_format.content_type,
                        "size_bytes": photo.size_bytes,
                    },
                )
            )
            view = uow.damage_photos.find_on_report(target.report_id, photo.id)
            if view is None:
                raise RuntimeError(
                    f"Attempted to read back damage photograph {photo.id} straight after writing "
                    "it in the same transaction, and it was not there."
                )
            uow.commit()
        return view

    @staticmethod
    def _left_in_bucket(photo: DamagePhoto, reason: str) -> None:
        """Log a stored object that no record will name, so it can be found later."""
        logger.warning(
            "damage_photo.object_left_without_record",
            extra={
                "object_key": photo.object_key,
                "damage_report_id": str(photo.damage_report_id),
                "reason": reason,
                "consequence": "the object stays in the bucket until the lifecycle rule removes it",
            },
        )
