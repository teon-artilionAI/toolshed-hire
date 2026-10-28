"""The dependencies of damage photographs, which are the store, the re-encoder and the use cases.

This is the photograph part of the composition root. The store is chosen once
when the application is built, from PHOTO_BUCKET, and kept on the application
state, the way the email gateway is. `PhotosSwitchedOn` hands a route the store
and refuses with 503 while it is switched off, so a route that depends on it
answers 503 before it reads a body or opens a transaction.

The re-encoder is one object for the process, because the semaphore inside it
is what limits how many photographs the process decodes at once.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Depends, Request

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.application.hire.damage_photo_ports import PhotoCleaner, PhotoStore
from app.application.hire.damage_photo_reads import (
    ReadDamagePhotos,
    ReadMyDamagePhotos,
    ensure_photos_switched_on,
)
from app.application.hire.upload_damage_photo import UploadDamagePhotoUseCase
from app.infrastructure.photo_images import PillowPhotoCleaner

# Where `create_app` keeps the photograph store on the application state.
PHOTO_STORE_STATE_KEY: Final[str] = "photo_store"

_CLEANER: Final[PillowPhotoCleaner] = PillowPhotoCleaner()


def get_photo_store(request: Request) -> PhotoStore:
    """Return the store the application was built with.

    Raises:
        RuntimeError: If the application carries no store. The application
            factory installs one, so this means an application was assembled
            some other way and then asked for a photograph.

    """
    store = getattr(request.app.state, PHOTO_STORE_STATE_KEY, None)
    if store is None:
        raise RuntimeError(
            "Attempted to handle a damage photograph in an application that was built without "
            f"a photograph store. Set `app.state.{PHOTO_STORE_STATE_KEY}` when the application "
            "is assembled, as `create_app` does."
        )
    photo_store: PhotoStore = store
    return photo_store


PhotoStoreDependency = Annotated[PhotoStore, Depends(get_photo_store)]


def require_photos_switched_on(store: PhotoStoreDependency) -> PhotoStore:
    """Return the store, or answer 503 when no bucket is configured.

    Raises:
        FeatureSwitchedOff: If photographs are switched off.

    """
    ensure_photos_switched_on(store)
    return store


PhotosSwitchedOn = Annotated[PhotoStore, Depends(require_photos_switched_on)]


def get_photo_cleaner() -> PhotoCleaner:
    """Return the re-encoder every photograph of this process goes through."""
    return _CLEANER


PhotoCleanerDependency = Annotated[PhotoCleaner, Depends(get_photo_cleaner)]


def get_upload_damage_photo_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    store: PhotoStoreDependency,
    cleaner: PhotoCleanerDependency,
) -> UploadDamagePhotoUseCase:
    """Return the use case that attaches a photograph to a report."""
    return UploadDamagePhotoUseCase(uow, clock, store, cleaner)


def get_read_damage_photos(
    uow: UnitOfWorkDependency, clock: ClockDependency, store: PhotoStoreDependency
) -> ReadDamagePhotos:
    """Return the reads of a report's photographs, for staff."""
    return ReadDamagePhotos(uow, clock, store)


def get_read_my_damage_photos(
    uow: UnitOfWorkDependency, clock: ClockDependency, store: PhotoStoreDependency
) -> ReadMyDamagePhotos:
    """Return the reads of the photographs on a customer's own hire."""
    return ReadMyDamagePhotos(uow, clock, store)


UploadDamagePhoto = Annotated[
    UploadDamagePhotoUseCase, Depends(get_upload_damage_photo_use_case)
]
ReadDamagePhotosDependency = Annotated[ReadDamagePhotos, Depends(get_read_damage_photos)]
ReadMyDamagePhotosDependency = Annotated[ReadMyDamagePhotos, Depends(get_read_my_damage_photos)]
