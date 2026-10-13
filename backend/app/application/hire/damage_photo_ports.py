"""The ports behind damage photographs, which are the rows, the bucket and the re-encoder.

`DamagePhotoRepository` keeps one row per photograph, inside the unit of work
of the report it belongs to. Attaching a photograph locks the report's row
first, so two photographs sent at once for one report are counted in turn and
the seventh is refused however they arrive. Every read takes one statement
however many photographs there are, and a read for a customer carries the
customer in its WHERE clause, as every read of a customer's records does (BR-42).

`PhotoStore` is the private bucket. It stores an object once, under a name the
domain chose, and makes a link to it that works for a short while and is
served as a download. A deployment with no bucket configured has a store that
is switched off, and every photograph route answers 503 with it.

`PhotoCleaner` re-encodes what the counter sent, which drops the EXIF block
with any GPS position in it, and refuses a file that cannot be decoded or that
would decode to more pixels than the service will hold in memory.

The application layer names the three, and the infrastructure layer provides
them. The image library and the storage client are imported there and nowhere
else.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol
from uuid import UUID

from app.application.hire.damage_models import DamageReportKey
from app.application.hire.damage_photo_models import DamagePhotoView, PhotoTarget
from app.application.ownership import OwnerScope
from app.domain.damage_photo import DamagePhoto, PhotoFormat


class DamagePhotoRepository(Protocol):
    """Where the record of each damage photograph is kept and read."""

    def target_of(self, key: DamageReportKey) -> PhotoTarget | None:
        """Return the report a photograph would be attached to, or None when there is none."""
        ...

    def lock_target(self, report_id: UUID) -> PhotoTarget | None:
        """Return the report locked for the rest of the transaction, or None when there is none.

        A second caller attaching a photograph to the same report waits here
        until the first has committed, and then counts its photograph too.
        """
        ...

    def add(self, photo: DamagePhoto) -> None:
        """Write the record of a stored photograph inside the current transaction."""
        ...

    def report_id_of(self, key: DamageReportKey) -> UUID | None:
        """Return the key of the report named by its key or reference, or None."""
        ...

    def of_report(self, report_id: UUID) -> tuple[DamagePhotoView, ...]:
        """Return the photographs of one report, in the order they were attached."""
        ...

    def find_on_report(self, report_id: UUID, photo_id: UUID) -> DamagePhotoView | None:
        """Return one photograph of one report, or None when the report has no such photograph."""
        ...

    def rental_is_visible(self, rental_id: UUID, scope: OwnerScope) -> bool:
        """Return True when the rental exists and the scope may read it."""
        ...

    def of_rental(self, rental_id: UUID, scope: OwnerScope) -> tuple[DamagePhotoView, ...]:
        """Return the photographs of every report on one rental, oldest first."""
        ...

    def find_on_rental(
        self, rental_id: UUID, photo_id: UUID, scope: OwnerScope
    ) -> DamagePhotoView | None:
        """Return one photograph of a report on the rental, or None when the scope finds none."""
        ...


class PhotoStore(Protocol):
    """The private bucket damage photographs are kept in."""

    @property
    def switched_on(self) -> bool:
        """Return True when a bucket is configured and photographs can be kept."""
        ...

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        """Store one photograph under a name that is not in use yet.

        Raises:
            FeatureSwitchedOff: If no bucket is configured.

        """
        ...

    def download_link(self, object_key: str, *, file_name: str, lifetime: timedelta) -> str:
        """Return a signed link to one photograph, served as a download under `file_name`.

        Raises:
            FeatureSwitchedOff: If no bucket is configured.

        """
        ...


class PhotoCleaner(Protocol):
    """Re-encodes a photograph so nothing but its pixels is kept."""

    def reencode(self, content: bytes, photo_format: PhotoFormat) -> bytes:
        """Return the photograph decoded, turned upright and encoded again with no metadata.

        Raises:
            ValidationFailure: If it cannot be decoded as the format its first
                bytes claim, or holds more pixels than the service will decode.

        """
        ...
