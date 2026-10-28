"""The re-encoder keeps a photograph's pixels and nothing else, and refuses what it cannot decode.

These run the real Pillow adapter on small images built in memory. A JPEG and
a PNG carrying a GPS position, a camera and a comment come out with none of it,
a photograph taken on its side comes out upright, a header that claims too
many pixels is refused before any are decoded, and a burst of photographs waits
its turn for the one decode slot rather than running at once.
"""

from __future__ import annotations

import threading
from typing import Final

import pytest

from app.domain.damage_photo import PhotoFormat
from app.domain.errors import TooManyAttempts, ValidationFailure
from app.infrastructure.photo_images import (
    TOO_MANY_PIXELS_MESSAGE,
    UNREADABLE_PHOTO_MESSAGE,
    PillowPhotoCleaner,
)
from tests.support.photo_files import (
    CAMERA_MODEL,
    HEIGHT,
    ROTATED_ORIENTATION,
    SVG_WITH_SCRIPT,
    WIDTH,
    jpeg_with_gps,
    metadata_of,
    mode_of,
    plain_jpeg,
    png_claiming_too_many_pixels,
    png_with_gps,
    size_of,
    truncated_jpeg,
)

# The marker of an EXIF block in a JPEG, and of the two text chunks in a PNG.
EXIF_MARKER: Final[bytes] = b"Exif\x00\x00"
PNG_EXIF_CHUNK: Final[bytes] = b"eXIf"
PNG_TEXT_CHUNK: Final[bytes] = b"tEXt"
JPEG_COMMENT_MARKER: Final[bytes] = b"\xff\xfe"
NO_WAIT: Final[float] = 0.01


@pytest.fixture
def cleaner() -> PillowPhotoCleaner:
    """Return a re-encoder with the limits the service runs with."""
    return PillowPhotoCleaner()


class TestNothingButThePixelsIsKept:
    """The GPS position, the camera, the comment and the text chunks are all left behind."""

    def test_a_jpeg_loses_its_exif_block_and_its_comment(self, cleaner: PillowPhotoCleaner) -> None:
        sent = jpeg_with_gps()
        assert EXIF_MARKER in sent and CAMERA_MODEL.encode() in sent

        kept = cleaner.reencode(sent, PhotoFormat.JPEG)

        assert EXIF_MARKER not in kept
        assert CAMERA_MODEL.encode() not in kept
        assert JPEG_COMMENT_MARKER not in kept
        assert not {"exif", "comment", "gps", "exif_tags", "icc_profile"} & set(metadata_of(kept))

    def test_a_png_loses_its_exif_chunk_and_its_text(self, cleaner: PillowPhotoCleaner) -> None:
        sent = png_with_gps()
        assert PNG_EXIF_CHUNK in sent and PNG_TEXT_CHUNK in sent

        kept = cleaner.reencode(sent, PhotoFormat.PNG)

        assert PNG_EXIF_CHUNK not in kept and PNG_TEXT_CHUNK not in kept
        assert metadata_of(kept) == {}

    def test_a_photograph_taken_on_its_side_is_stored_upright(
        self, cleaner: PillowPhotoCleaner
    ) -> None:
        kept = cleaner.reencode(jpeg_with_gps(orientation=ROTATED_ORIENTATION), PhotoFormat.JPEG)
        assert size_of(kept) == (HEIGHT, WIDTH)

    def test_a_photograph_with_no_orientation_keeps_its_shape(
        self, cleaner: PillowPhotoCleaner
    ) -> None:
        assert size_of(cleaner.reencode(plain_jpeg(), PhotoFormat.JPEG)) == (WIDTH, HEIGHT)

    def test_a_transparent_png_keeps_its_alpha_and_an_opaque_one_gains_none(
        self, cleaner: PillowPhotoCleaner
    ) -> None:
        assert mode_of(cleaner.reencode(png_with_gps(transparent=True), PhotoFormat.PNG)) == "RGBA"
        assert mode_of(cleaner.reencode(png_with_gps(), PhotoFormat.PNG)) == "RGB"


class TestWhatCannotBeDecoded:
    """A refusal in a plain sentence, never a fault."""

    def test_a_jpeg_cut_short_is_refused(self, cleaner: PillowPhotoCleaner) -> None:
        with pytest.raises(ValidationFailure) as refused:
            cleaner.reencode(truncated_jpeg(), PhotoFormat.JPEG)
        assert refused.value.message == UNREADABLE_PHOTO_MESSAGE

    def test_a_png_handed_over_as_a_jpeg_is_not_decoded_as_a_png(
        self, cleaner: PillowPhotoCleaner
    ) -> None:
        with pytest.raises(ValidationFailure):
            cleaner.reencode(png_with_gps(), PhotoFormat.JPEG)

    def test_an_svg_never_reaches_a_decoder_that_accepts_it(
        self, cleaner: PillowPhotoCleaner
    ) -> None:
        with pytest.raises(ValidationFailure):
            cleaner.reencode(SVG_WITH_SCRIPT, PhotoFormat.PNG)

    def test_a_header_claiming_too_many_pixels_is_refused(
        self, cleaner: PillowPhotoCleaner
    ) -> None:
        with pytest.raises(ValidationFailure) as refused:
            cleaner.reencode(png_claiming_too_many_pixels(), PhotoFormat.PNG)
        assert refused.value.message == TOO_MANY_PIXELS_MESSAGE
        assert refused.value.detail["width"] == 6000

    def test_the_pixel_limit_is_the_one_the_cleaner_was_built_with(self) -> None:
        tight = PillowPhotoCleaner(maximum_pixels=WIDTH * HEIGHT - 1)
        with pytest.raises(ValidationFailure):
            tight.reencode(plain_jpeg(), PhotoFormat.JPEG)

    @pytest.mark.parametrize(("pixels", "slots"), [(0, 1), (1, 0)])
    def test_a_limit_that_is_not_positive_is_refused_at_once(
        self, pixels: int, slots: int
    ) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            PillowPhotoCleaner(maximum_pixels=pixels, decode_slots=slots)


class TestOnePhotographAtATime:
    """The decode slot bounds the memory a burst of uploads can take."""

    def test_a_caller_that_waits_too_long_is_told_to_try_again(self) -> None:
        cleaner = PillowPhotoCleaner(decode_slots=1, decode_wait_seconds=NO_WAIT)
        holding = threading.Event()
        release = threading.Event()

        def hold_the_slot() -> None:
            """Take the only slot and keep it until the test lets go."""
            with cleaner._decode_slot():
                holding.set()
                release.wait()

        holder = threading.Thread(target=hold_the_slot)
        holder.start()
        try:
            assert holding.wait(timeout=5)
            with pytest.raises(TooManyAttempts) as refused:
                cleaner.reencode(plain_jpeg(), PhotoFormat.JPEG)
            assert refused.value.retry_after_seconds > 0
        finally:
            release.set()
            holder.join()
        assert cleaner.reencode(plain_jpeg(), PhotoFormat.JPEG)
