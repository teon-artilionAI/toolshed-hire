"""Photographs and things that pretend to be photographs, built in memory for the tests.

A phone's photograph carries an EXIF block, often with the GPS position it was
taken at. `jpeg_with_gps` and `png_with_gps` build small images that carry one,
with the make and model of a camera, an orientation tag and a comment or text
chunk beside it, so a test can prove that none of it survives. The rest are
the files the upload must refuse. An SVG with a script in it renamed to end in
.jpg, a JPEG cut short, and a PNG whose header claims more pixels than the
service will decode, written by hand so the test never builds the image itself.
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import Final

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.domain.damage_photo import JPEG_SIGNATURE, MAXIMUM_PHOTO_BYTES, PNG_SIGNATURE

# EXIF tags, by their numbers in the specification.
ORIENTATION_TAG: Final[int] = 0x0112
MAKE_TAG: Final[int] = 0x010F
MODEL_TAG: Final[int] = 0x0110
GPS_IFD_TAG: Final[int] = 0x8825
GPS_LATITUDE_REF: Final[int] = 1
GPS_LATITUDE: Final[int] = 2
GPS_LONGITUDE_REF: Final[int] = 3
GPS_LONGITUDE: Final[int] = 4
# The orientation a phone writes when it was held on its side, which a viewer
# turns by 90 degrees.
ROTATED_ORIENTATION: Final[int] = 6

CAMERA_MAKE: Final[str] = "Snoopy Phones"
CAMERA_MODEL: Final[str] = "SP-12 serial 0042"
COMMENT: Final[str] = "Taken outside 12 Long Street by Thandi"
WIDTH: Final[int] = 64
HEIGHT: Final[int] = 32
PHOTO_COLOUR: Final[tuple[int, int, int]] = (200, 120, 40)

SVG_WITH_SCRIPT: Final[bytes] = (
    b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
    b"<script>fetch('/api/me')</script></svg>"
)
# A header that claims 6000 by 5000 pixels, 30 million, which is past the limit
# and under Pillow's own, so the service's check is the one that refuses it.
CLAIMED_WIDTH: Final[int] = 6000
CLAIMED_HEIGHT: Final[int] = 5000
PNG_BIT_DEPTH: Final[int] = 8
PNG_RGB_COLOUR_TYPE: Final[int] = 2


def gps_exif(*, orientation: int | None = None) -> Image.Exif:
    """Return an EXIF block with a camera, a GPS position in Cape Town and an orientation."""
    exif = Image.Exif()
    exif[MAKE_TAG] = CAMERA_MAKE
    exif[MODEL_TAG] = CAMERA_MODEL
    if orientation is not None:
        exif[ORIENTATION_TAG] = orientation
    gps = exif.get_ifd(GPS_IFD_TAG)
    gps[GPS_LATITUDE_REF] = "S"
    gps[GPS_LATITUDE] = (33.0, 55.0, 12.0)
    gps[GPS_LONGITUDE_REF] = "E"
    gps[GPS_LONGITUDE] = (18.0, 25.0, 25.0)
    return exif


def jpeg_with_gps(
    *, orientation: int | None = None, size: tuple[int, int] = (WIDTH, HEIGHT)
) -> bytes:
    """Return a JPEG that carries a GPS position, a camera, a comment and maybe an orientation."""
    out = io.BytesIO()
    image = Image.new("RGB", size, PHOTO_COLOUR)
    image.save(
        out,
        format="JPEG",
        exif=gps_exif(orientation=orientation).tobytes(),
        comment=COMMENT.encode("utf-8"),
    )
    return out.getvalue()


def png_with_gps(*, transparent: bool = False) -> bytes:
    """Return a PNG that carries a GPS position in an eXIf chunk and a comment in a text chunk."""
    text = PngInfo()
    text.add_text("Comment", COMMENT)
    out = io.BytesIO()
    mode, colour = ("RGBA", (*PHOTO_COLOUR, 128)) if transparent else ("RGB", PHOTO_COLOUR)
    Image.new(mode, (WIDTH, HEIGHT), colour).save(
        out, format="PNG", exif=gps_exif().tobytes(), pnginfo=text
    )
    return out.getvalue()


def plain_jpeg() -> bytes:
    """Return a small JPEG with nothing but its pixels."""
    out = io.BytesIO()
    Image.new("RGB", (WIDTH, HEIGHT), PHOTO_COLOUR).save(out, format="JPEG")
    return out.getvalue()


def truncated_jpeg() -> bytes:
    """Return a JPEG cut off part of the way through its pixels."""
    whole = jpeg_with_gps(size=(256, 256))
    return whole[: len(whole) // 2]


def png_claiming_too_many_pixels() -> bytes:
    """Return a PNG whose header claims 30 megapixels and which holds no pixels at all."""
    header = struct.pack(
        ">IIBBBBB", CLAIMED_WIDTH, CLAIMED_HEIGHT, PNG_BIT_DEPTH, PNG_RGB_COLOUR_TYPE, 0, 0, 0
    )
    return PNG_SIGNATURE + _png_chunk(b"IHDR", header) + _png_chunk(b"IEND", b"")


def oversized_jpeg() -> bytes:
    """Return a file that starts like a JPEG and is one byte past the limit."""
    return JPEG_SIGNATURE + b"\x00" * (MAXIMUM_PHOTO_BYTES + 1 - len(JPEG_SIGNATURE))


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    """Return one PNG chunk with its length and its CRC."""
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def metadata_of(content: bytes) -> dict[str, object]:
    """Return what a stored photograph still carries besides its pixels, empty when nothing."""
    with Image.open(io.BytesIO(content)) as image:
        found: dict[str, object] = dict(image.info)
        exif = image.getexif()
        if len(exif):
            found["exif_tags"] = sorted(exif)
        if len(exif.get_ifd(GPS_IFD_TAG)):
            found["gps"] = dict(exif.get_ifd(GPS_IFD_TAG))
        text = getattr(image, "text", {})
        if text:
            found["text"] = dict(text)
    return found


def size_of(content: bytes) -> tuple[int, int]:
    """Return the width and the height of a stored photograph."""
    with Image.open(io.BytesIO(content)) as image:
        width, height = image.size
    return width, height


def mode_of(content: bytes) -> str:
    """Return the colour mode of a stored photograph."""
    with Image.open(io.BytesIO(content)) as image:
        return str(image.mode)


__all__ = [
    "CAMERA_MODEL",
    "HEIGHT",
    "ROTATED_ORIENTATION",
    "SVG_WITH_SCRIPT",
    "WIDTH",
    "jpeg_with_gps",
    "metadata_of",
    "mode_of",
    "oversized_jpeg",
    "plain_jpeg",
    "png_claiming_too_many_pixels",
    "png_with_gps",
    "size_of",
    "truncated_jpeg",
]
