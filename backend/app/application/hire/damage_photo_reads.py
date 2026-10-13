"""Reading damage photographs, for staff on a report and for a customer on their own hire.

Staff read the photographs of any report, as they read any report (BR-43). A
customer reads the photographs of every report filed against their own hire,
because those photographs are the evidence for what was kept back from their
deposit (#112). The customer's reads go through the owner scope, so another
customer's hire or photograph is not found, in the same words as one that
never existed (BR-42).

A list holds no links. A link is made for one photograph when it is opened,
works for five minutes and is served as a download (C-31). Every link handed
out is logged with who asked for it, because opening one is reading a record
about a customer.

A deployment with no bucket answers every read with 503 through the store,
before anything is read.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from app.application.clock import Clock
from app.application.hire.damage_models import DamageReportKey
from app.application.hire.damage_photo_models import DamagePhotoView, PhotoLink
from app.application.hire.damage_photo_ports import PhotoStore
from app.application.hire.damage_reads import REPORT_NOT_FOUND_MESSAGE
from app.application.hire.read_rental import RENTAL_NOT_FOUND_MESSAGE
from app.application.ownership import OwnerScope, owner_scope_for
from app.application.unit_of_work import UnitOfWork
from app.domain.damage_photo import PHOTO_LINK_LIFETIME
from app.domain.errors import FeatureSwitchedOff, NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

PHOTOS_SWITCHED_OFF_MESSAGE: Final[str] = "Photographs are not switched on yet."
PHOTO_NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find that photograph. Open the list of photographs again and choose it there."
)


def ensure_photos_switched_on(store: PhotoStore) -> None:
    """Refuse every photograph request while no bucket is configured.

    Raises:
        FeatureSwitchedOff: If the store is switched off.

    """
    if not store.switched_on:
        raise FeatureSwitchedOff(PHOTOS_SWITCHED_OFF_MESSAGE, {"feature": "damage_photos"})


class ReadDamagePhotos:
    """Return the photographs of a report to staff, and a link to one of them."""

    def __init__(self, uow: UnitOfWork, clock: Clock, store: PhotoStore) -> None:
        """Keep the unit of work, the clock and the bucket the reads run with."""
        self._uow = uow
        self._clock = clock
        self._store = store

    def of_report(self, actor: Actor, key: DamageReportKey) -> tuple[DamagePhotoView, ...]:
        """Return every photograph of one report, in the order they were attached.

        Raises:
            FeatureSwitchedOff: If no bucket is configured.
            NotFound: If there is no such report.

        """
        ensure_photos_switched_on(self._store)
        logger.info(
            "damage_photo.list_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "damage_report": str(key),
            },
        )
        with self._uow as uow:
            report_id = _report_id(uow, key)
            photos = uow.damage_photos.of_report(report_id)
        logger.info(
            "damage_photo.list_finished",
            extra={"damage_report_id": str(report_id), "photo_count": len(photos)},
        )
        return photos

    def link(self, actor: Actor, key: DamageReportKey, photo_id: UUID) -> PhotoLink:
        """Return a five minute link to one photograph of one report.

        Raises:
            FeatureSwitchedOff: If no bucket is configured.
            NotFound: If there is no such report, or it has no such photograph.

        """
        ensure_photos_switched_on(self._store)
        with self._uow as uow:
            report_id = _report_id(uow, key)
            photo = uow.damage_photos.find_on_report(report_id, photo_id)
        if photo is None:
            raise _photo_not_found(photo_id)
        return _link_to(self._store, self._clock, actor, photo)


class ReadMyDamagePhotos:
    """Return the photographs of damage on a customer's own hire, and a link to one."""

    def __init__(self, uow: UnitOfWork, clock: Clock, store: PhotoStore) -> None:
        """Keep the unit of work, the clock and the bucket the reads run with."""
        self._uow = uow
        self._clock = clock
        self._store = store

    def of_rental(self, actor: Actor, rental_id: UUID) -> tuple[DamagePhotoView, ...]:
        """Return the photographs of every report on the hire, oldest first.

        Raises:
            FeatureSwitchedOff: If no bucket is configured.
            NotFound: If the hire does not exist or is not the customer's.

        """
        ensure_photos_switched_on(self._store)
        scope = owner_scope_for(actor)
        logger.info(
            "damage_photo.customer_list_requested",
            extra={"actor_user_id": str(actor.user_id), "rental_id": str(rental_id)},
        )
        with self._uow as uow:
            _ensure_visible(uow, rental_id, scope)
            photos = uow.damage_photos.of_rental(rental_id, scope)
        logger.info(
            "damage_photo.customer_list_finished",
            extra={"rental_id": str(rental_id), "photo_count": len(photos)},
        )
        return photos

    def link(self, actor: Actor, rental_id: UUID, photo_id: UUID) -> PhotoLink:
        """Return a five minute link to one photograph of damage on the customer's own hire.

        Raises:
            FeatureSwitchedOff: If no bucket is configured.
            NotFound: If the hire is not the customer's, or holds no such photograph.

        """
        ensure_photos_switched_on(self._store)
        scope = owner_scope_for(actor)
        with self._uow as uow:
            _ensure_visible(uow, rental_id, scope)
            photo = uow.damage_photos.find_on_rental(rental_id, photo_id, scope)
        if photo is None:
            raise _photo_not_found(photo_id)
        return _link_to(self._store, self._clock, actor, photo)


def _report_id(uow: UnitOfWork, key: DamageReportKey) -> UUID:
    """Return the key of the report named by its key or reference.

    Raises:
        NotFound: If there is no such report.

    """
    report_id = uow.damage_photos.report_id_of(key)
    if report_id is None:
        logger.info("damage_photo.report_not_found", extra={"damage_report": str(key)})
        raise NotFound(REPORT_NOT_FOUND_MESSAGE, {"damage_report": str(key)})
    return report_id


def _ensure_visible(uow: UnitOfWork, rental_id: UUID, scope: OwnerScope) -> None:
    """Refuse a hire the reader may not see, in the words for one that does not exist.

    Raises:
        NotFound: If the hire does not exist or the scope does not reach it.

    """
    if not uow.damage_photos.rental_is_visible(rental_id, scope):
        logger.info(
            "damage_photo.rental_not_found",
            extra={"rental_id": str(rental_id), "scoped": scope.is_restricted},
        )
        raise NotFound(RENTAL_NOT_FOUND_MESSAGE, {"rental": str(rental_id)})


def _photo_not_found(photo_id: UUID) -> NotFound:
    """Build the one answer for a photograph that is absent or out of the reader's reach.

    It says the same thing in both cases on purpose, as every read of a
    customer's records does (BR-42).
    """
    logger.info("damage_photo.not_found", extra={"damage_photo_id": str(photo_id)})
    return NotFound(PHOTO_NOT_FOUND_MESSAGE, {"damage_photo": str(photo_id)})


def _link_to(store: PhotoStore, clock: Clock, actor: Actor, photo: DamagePhotoView) -> PhotoLink:
    """Make a link to one photograph and log who it was made for."""
    issued_at = clock.now()
    url = store.download_link(
        photo.object_key, file_name=photo.download_name, lifetime=PHOTO_LINK_LIFETIME
    )
    link = PhotoLink(url=url, expires_at=issued_at + PHOTO_LINK_LIFETIME)
    logger.info(
        "damage_photo.link_issued",
        extra={
            "actor_user_id": str(actor.user_id),
            "actor_role": actor.role.value,
            "damage_photo_id": str(photo.id),
            "damage_report_reference": photo.damage_report_reference,
            "expires_at": link.expires_at.isoformat(),
        },
    )
    return link
