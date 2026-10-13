"""The re-encoder of damage photographs, the only module that imports Pillow (C-30).

A phone writes far more into a photograph than its pixels. The EXIF block can
hold the GPS position it was taken at, the make and serial of the camera and a
thumbnail of the uncropped image, and a PNG can carry text chunks with anything
in them. None of that is evidence of damage, and some of it is about a person.
So every photograph is decoded and encoded again from its pixels alone, and
nothing else is copied across.

The steps, in order:

1. The decoder is limited to the format the first bytes named, so a file that
   starts like a JPEG is never handed to another of Pillow's decoders.
2. The pixel count is read from the header and checked before anything is
   decoded, which is the guard against a decompression bomb, a small file that
   decodes to gigabytes. MAXIMUM_PIXELS is below Pillow's own limit, so its
   warning is never the only defence.
3. The EXIF orientation is applied, so a photograph taken with the phone on its
   side is stored the right way up once the tag that said so is gone.
4. The image is encoded again, a JPEG at quality 85 and a PNG losslessly, with
   no EXIF, no ICC profile, no comment and no text chunk.

Decoding a 24 megapixel photograph takes about 70 MB, and the transposed copy as
much again, while a Cloud Run instance has 512 MB and serves 80 requests at
once. One photograph is decoded at a time in each process, through a semaphore,
so a burst of uploads queues for a second or two and cannot exhaust the memory.
A caller that waits longer than DECODE_WAIT_SECONDS is told to try again.
"""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.damage_photo import PhotoFormat
from app.domain.errors import TooManyAttempts, ValidationFailure

logger = logging.getLogger(__name__)

# 6000 by 4000, more than any phone writes at its default setting.
MAXIMUM_PIXELS: Final[int] = 24_000_000
# High enough that a crack or a scratch stays sharp, low enough to keep the
# stored copy near the size of what the phone sent.
JPEG_QUALITY: Final[int] = 85
DECODE_SLOTS: Final[int] = 1
DECODE_WAIT_SECONDS: Final[float] = 20.0
RETRY_AFTER_SECONDS: Final[int] = 5
MILLISECONDS: Final[int] = 1000

PILLOW_FORMATS: Final[dict[PhotoFormat, str]] = {
    PhotoFormat.JPEG: "JPEG",
    PhotoFormat.PNG: "PNG",
}
OPAQUE_MODE: Final[str] = "RGB"
TRANSPARENT_MODE: Final[str] = "RGBA"
MODES_WITH_ALPHA: Final[frozenset[str]] = frozenset({"RGBA", "LA", "PA", "RGBa", "La"})
PALETTE_MODE: Final[str] = "P"
TRANSPARENCY_KEY: Final[str] = "transparency"

UNREADABLE_PHOTO_MESSAGE: Final[str] = (
    "That photograph could not be opened. It may be damaged or only partly sent. Take it "
    "again and try once more."
)
TOO_MANY_PIXELS_MESSAGE: Final[str] = (
    "That photograph has more pixels than we keep. Take it again at the camera's normal "
    "setting, not its highest resolution."
)
BUSY_MESSAGE: Final[str] = (
    "We are busy with other photographs. Wait a few seconds and send this one again."
)

# What Pillow raises for a file it cannot decode. A truncated file is an
# OSError, a malformed header a SyntaxError or a ValueError, and a file over
# Pillow's own pixel limit a DecompressionBombError.
DECODE_FAILURES: Final[tuple[type[Exception], ...]] = (
    UnidentifiedImageError,
    Image.DecompressionBombError,
    OSError,
    SyntaxError,
    ValueError,
)


class PillowPhotoCleaner:
    """Decode a photograph and encode it again from its pixels alone."""

    def __init__(
        self,
        *,
        maximum_pixels: int = MAXIMUM_PIXELS,
        decode_slots: int = DECODE_SLOTS,
        decode_wait_seconds: float = DECODE_WAIT_SECONDS,
    ) -> None:
        """Set the pixel limit and how many photographs this process decodes at once.

        Raises:
            ValueError: If the limit or the number of slots is not positive.

        """
        if maximum_pixels <= 0 or decode_slots <= 0:
            raise ValueError(
                f"Attempted to build the photograph re-encoder with a pixel limit of "
                f"{maximum_pixels} and {decode_slots} decode slots. Both must be positive."
            )
        self._maximum_pixels = maximum_pixels
        self._slots = threading.BoundedSemaphore(decode_slots)
        self._wait_seconds = decode_wait_seconds

    def reencode(self, content: bytes, photo_format: PhotoFormat) -> bytes:
        """Return the photograph turned upright and encoded again with no metadata.

        Raises:
            ValidationFailure: If it cannot be decoded as `photo_format`, or holds
                more pixels than the limit.
            TooManyAttempts: If no decode slot came free in time.

        """
        started = perf_counter()
        with self._decode_slot():
            cleaned = self._reencode(content, photo_format)
        logger.info(
            "damage_photo.reencoded",
            extra={
                "photo_format": photo_format.value,
                "received_bytes": len(content),
                "stored_bytes": len(cleaned),
                "duration_ms": round((perf_counter() - started) * MILLISECONDS),
            },
        )
        return cleaned

    @contextmanager
    def _decode_slot(self) -> Iterator[None]:
        """Hold one of the decode slots for the length of the block.

        Raises:
            TooManyAttempts: If no slot came free within the wait.

        """
        if not self._slots.acquire(timeout=self._wait_seconds):
            logger.warning(
                "damage_photo.decode_busy",
                extra={"waited_seconds": self._wait_seconds, "retry_after": RETRY_AFTER_SECONDS},
            )
            raise TooManyAttempts(BUSY_MESSAGE, retry_after_seconds=RETRY_AFTER_SECONDS)
        try:
            yield
        finally:
            self._slots.release()

    def _reencode(self, content: bytes, photo_format: PhotoFormat) -> bytes:
        """Decode, check, turn upright and encode one photograph.

        Raises:
            ValidationFailure: If it cannot be decoded or holds too many pixels.

        """
        pillow_format = PILLOW_FORMATS[photo_format]
        try:
            with Image.open(io.BytesIO(content), formats=[pillow_format]) as image:
                self._ensure_pixels_within_limit(image, photo_format)
                image.load()
                upright = ImageOps.exif_transpose(image)
                clean = upright.convert(_target_mode(upright, photo_format))
        except DECODE_FAILURES as failure:
            logger.info(
                "damage_photo.unreadable",
                extra={
                    "photo_format": photo_format.value,
                    "size_bytes": len(content),
                    "cause": type(failure).__name__,
                },
            )
            raise ValidationFailure(
                UNREADABLE_PHOTO_MESSAGE, {"photo_format": photo_format.value}
            ) from failure
        # convert() hands the new image a copy of the old one's info, which holds
        # the EXIF block, the ICC profile and any comment or text. None of it is kept.
        clean.info = {}
        encoded = io.BytesIO()
        if photo_format is PhotoFormat.JPEG:
            clean.save(encoded, format=pillow_format, quality=JPEG_QUALITY)
        else:
            clean.save(encoded, format=pillow_format)
        return encoded.getvalue()

    def _ensure_pixels_within_limit(self, image: Image.Image, photo_format: PhotoFormat) -> None:
        """Refuse a photograph whose header claims more pixels than the limit.

        Raises:
            ValidationFailure: If width times height is above the limit.

        """
        width, height = image.size
        if width * height > self._maximum_pixels:
            logger.info(
                "damage_photo.too_many_pixels",
                extra={
                    "photo_format": photo_format.value,
                    "width": width,
                    "height": height,
                    "maximum_pixels": self._maximum_pixels,
                },
            )
            raise ValidationFailure(
                TOO_MANY_PIXELS_MESSAGE,
                {"width": width, "height": height, "maximum_pixels": self._maximum_pixels},
            )


def _target_mode(image: Image.Image, photo_format: PhotoFormat) -> str:
    """Return the colour mode a photograph is stored in.

    A JPEG holds no transparency, so it is stored as RGB. A PNG keeps an alpha
    channel when it has one, including a palette with a transparent colour.
    """
    if photo_format is PhotoFormat.JPEG:
        return OPAQUE_MODE
    has_alpha = image.mode in MODES_WITH_ALPHA or (
        image.mode == PALETTE_MODE and TRANSPARENCY_KEY in image.info
    )
    return TRANSPARENT_MODE if has_alpha else OPAQUE_MODE
