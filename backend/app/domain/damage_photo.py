"""The photographs counter staff attach to a damage report (C-29, C-30, C-31).

A photograph is the evidence behind a deduction from a deposit, so what is
kept has to be what the counter took and nothing more. Three rules hold here.

A photograph is a JPEG or a PNG, and its first bytes decide which. The name of
the file and the type the browser claimed are never trusted, so an SVG, which
can carry script, or anything else renamed to end in .jpg is refused (C-30).

A photograph is at most 4 MB as it arrives, and a report holds at most six.
The seventh is refused with the six already there, not by dropping one.

A photograph is stored under a name nobody can guess, in a private bucket, and
read through a link that works for five minutes (C-31). The name says which
report it belongs to and nothing about the customer.

Re-encoding the image, which removes its metadata, and the storage itself are
outside the domain. This module holds the rules and the record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Final
from uuid import UUID

from app.domain.errors import PhotoLimitReached, PhotoTooLarge, UnsupportedPhoto

BYTES_IN_A_MEGABYTE: Final[int] = 1024 * 1024
MAXIMUM_PHOTO_MEGABYTES: Final[int] = 4
MAXIMUM_PHOTO_BYTES: Final[int] = MAXIMUM_PHOTO_MEGABYTES * BYTES_IN_A_MEGABYTE
MAXIMUM_PHOTOS_PER_REPORT: Final[int] = 6
# How long a link to one photograph works.
PHOTO_LINK_LIFETIME: Final[timedelta] = timedelta(minutes=5)
# Every object of the bucket that holds damage photographs starts with this.
OBJECT_KEY_PREFIX: Final[str] = "damage"

# The first bytes of each format, as the two specifications define them.
JPEG_SIGNATURE: Final[bytes] = b"\xff\xd8\xff"
PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"

PHOTO_TOO_LARGE_MESSAGE: Final[str] = (
    f"That photograph is larger than {MAXIMUM_PHOTO_MEGABYTES} MB. Take it again at a lower "
    "resolution, or send a smaller copy."
)
UNSUPPORTED_PHOTO_MESSAGE: Final[str] = (
    "That file is not a JPEG or PNG photograph. Choose a photograph taken with a camera or a "
    "phone."
)
EMPTY_PHOTO_MESSAGE: Final[str] = "No photograph arrived. Choose the photograph and try again."
PHOTO_LIMIT_MESSAGE: Final[str] = (
    f"This damage report already has {MAXIMUM_PHOTOS_PER_REPORT} photographs, which is as many "
    "as a report can hold."
)
PHOTO_LIMIT_RULE: Final[str] = "C-30"


class PhotoFormat(str, Enum):
    """The two formats a damage photograph may arrive and be stored in."""

    JPEG = "JPEG"
    PNG = "PNG"

    @property
    def content_type(self) -> str:
        """Return the media type the photograph is stored and served as."""
        return _CONTENT_TYPES[self]

    @property
    def extension(self) -> str:
        """Return the extension the stored object and a downloaded copy carry."""
        return _EXTENSIONS[self]


_CONTENT_TYPES: Final[dict[PhotoFormat, str]] = {
    PhotoFormat.JPEG: "image/jpeg",
    PhotoFormat.PNG: "image/png",
}
_EXTENSIONS: Final[dict[PhotoFormat, str]] = {PhotoFormat.JPEG: "jpg", PhotoFormat.PNG: "png"}
# The media types a client may send a photograph as. They admit the request,
# and the bytes still decide the format.
ACCEPTED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(_CONTENT_TYPES.values())


def photo_format_of(content: bytes) -> PhotoFormat:
    """Return the format of a photograph, decided by its first bytes alone.

    Raises:
        UnsupportedPhoto: If the content is empty, or starts like neither a
            JPEG nor a PNG.

    """
    if not content:
        raise UnsupportedPhoto(EMPTY_PHOTO_MESSAGE, {"size_bytes": 0})
    if content.startswith(JPEG_SIGNATURE):
        return PhotoFormat.JPEG
    if content.startswith(PNG_SIGNATURE):
        return PhotoFormat.PNG
    raise UnsupportedPhoto(UNSUPPORTED_PHOTO_MESSAGE, {"size_bytes": len(content)})


def ensure_photo_size(size_bytes: int) -> None:
    """Refuse a photograph larger than the limit.

    Raises:
        PhotoTooLarge: If it is larger than MAXIMUM_PHOTO_BYTES.

    """
    if size_bytes > MAXIMUM_PHOTO_BYTES:
        raise PhotoTooLarge(
            PHOTO_TOO_LARGE_MESSAGE,
            {"size_bytes": size_bytes, "maximum_bytes": MAXIMUM_PHOTO_BYTES},
        )


def ensure_room_for_another_photo(photos_held: int) -> None:
    """Refuse a photograph for a report that already holds as many as it may.

    Raises:
        PhotoLimitReached: If the report holds MAXIMUM_PHOTOS_PER_REPORT already.

    """
    if photos_held >= MAXIMUM_PHOTOS_PER_REPORT:
        raise PhotoLimitReached(
            PHOTO_LIMIT_MESSAGE,
            {"photos_held": photos_held, "maximum_photos": MAXIMUM_PHOTOS_PER_REPORT},
            rule=PHOTO_LIMIT_RULE,
        )


def photo_object_key(report_id: UUID, photo_id: UUID, photo_format: PhotoFormat) -> str:
    """Return the name a photograph is stored under, for example damage/<report>/<photo>.jpg.

    The photograph's own key is random, so the name cannot be guessed from the
    report, and it never carries anything the customer or the counter typed.
    """
    return f"{OBJECT_KEY_PREFIX}/{report_id}/{photo_id}.{photo_format.extension}"


@dataclass(frozen=True, slots=True)
class DamagePhoto:
    """One photograph attached to a damage report.

    Attributes:
        id: The photograph's key, random.
        damage_report_id: The report it is evidence for.
        object_key: Where it is stored in the private bucket.
        photo_format: Whether it is stored as a JPEG or a PNG.
        size_bytes: How large the stored, re-encoded copy is.
        uploaded_by_user_id: The member of staff who attached it.
        uploaded_at: When it was attached.

    """

    id: UUID
    damage_report_id: UUID
    object_key: str
    photo_format: PhotoFormat
    size_bytes: int
    uploaded_by_user_id: UUID
    uploaded_at: datetime
