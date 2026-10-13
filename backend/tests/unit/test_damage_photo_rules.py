"""The rules of a damage photograph, which are its format by its first bytes, its size and count.

The name of a file and the type a browser claims are never trusted, so these
tests hand the rule the bytes alone. An SVG, a GIF and a file that merely
mentions JPEG are refused, and the two signatures are matched exactly.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest

from app.domain.damage_photo import (
    JPEG_SIGNATURE,
    MAXIMUM_PHOTO_BYTES,
    MAXIMUM_PHOTOS_PER_REPORT,
    PNG_SIGNATURE,
    PhotoFormat,
    ensure_photo_size,
    ensure_room_for_another_photo,
    photo_format_of,
    photo_object_key,
)
from app.domain.errors import PhotoLimitReached, PhotoTooLarge, UnsupportedPhoto
from tests.support.photo_files import SVG_WITH_SCRIPT

REPORT: Final[UUID] = UUID("6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f")
PHOTO: Final[UUID] = UUID("0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d")


class TestTheFormatIsDecidedByTheFirstBytes:
    """JPEG starts FF D8 FF, PNG starts 89 50 4E 47 0D 0A 1A 0A, and nothing else is either."""

    def test_a_jpeg_signature_is_a_jpeg(self) -> None:
        assert photo_format_of(JPEG_SIGNATURE + b"\xe0rest") is PhotoFormat.JPEG

    def test_a_png_signature_is_a_png(self) -> None:
        assert photo_format_of(PNG_SIGNATURE + b"\x00\x00\x00\rIHDR") is PhotoFormat.PNG

    @pytest.mark.parametrize(
        "content",
        [
            SVG_WITH_SCRIPT,
            b"GIF89a\x01\x00\x01\x00",
            b"RIFF\x00\x00\x00\x00WEBPVP8 ",
            b"%PDF-1.7",
            b"\xff\xd8",
            PNG_SIGNATURE[:-1],
            b" " + JPEG_SIGNATURE,
            b"<html>JPEG</html>",
        ],
        ids=["svg", "gif", "webp", "pdf", "short-jpeg", "short-png", "leading-space", "html"],
    )
    def test_anything_else_is_refused(self, content: bytes) -> None:
        with pytest.raises(UnsupportedPhoto):
            photo_format_of(content)

    def test_nothing_at_all_is_refused(self) -> None:
        with pytest.raises(UnsupportedPhoto) as refused:
            photo_format_of(b"")
        assert refused.value.detail == {"size_bytes": 0}

    def test_each_format_is_stored_as_its_own_media_type(self) -> None:
        assert (PhotoFormat.JPEG.content_type, PhotoFormat.JPEG.extension) == ("image/jpeg", "jpg")
        assert (PhotoFormat.PNG.content_type, PhotoFormat.PNG.extension) == ("image/png", "png")


class TestTheLimits:
    """Four megabytes a photograph and six photographs a report."""

    def test_exactly_four_megabytes_is_accepted(self) -> None:
        ensure_photo_size(MAXIMUM_PHOTO_BYTES)
        assert MAXIMUM_PHOTO_BYTES == 4 * 1024 * 1024

    def test_one_byte_more_is_refused(self) -> None:
        with pytest.raises(PhotoTooLarge):
            ensure_photo_size(MAXIMUM_PHOTO_BYTES + 1)

    def test_a_report_with_five_has_room_for_a_sixth(self) -> None:
        ensure_room_for_another_photo(MAXIMUM_PHOTOS_PER_REPORT - 1)

    def test_a_report_with_six_has_no_room(self) -> None:
        with pytest.raises(PhotoLimitReached) as refused:
            ensure_room_for_another_photo(MAXIMUM_PHOTOS_PER_REPORT)
        assert refused.value.detail == {"photos_held": 6, "maximum_photos": 6}


class TestTheStoredName:
    """The name says which report and nothing a person typed."""

    def test_the_name_is_the_report_and_the_photographs_own_key(self) -> None:
        assert photo_object_key(REPORT, PHOTO, PhotoFormat.PNG) == f"damage/{REPORT}/{PHOTO}.png"
