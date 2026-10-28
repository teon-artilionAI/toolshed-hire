"""Reading a damage photograph off the request, as raw bytes with a hard cap (C-29).

The photograph is the whole body, sent with `Content-Type: image/jpeg` or
`image/png`. Multipart would need python-multipart, a further dependency, for
one field. The media type only admits the request. Which format the photograph
is, is decided later from its first bytes.

A `Content-Length` over the cap is refused before a byte is read. A body with
no length, or one that lies about it, is read as a stream and refused as soon
as it passes the cap, so the service never holds more than 4 MB and one chunk
of any upload in memory.

This is an async dependency so it can read the stream. The routes that use it
are plain functions and run in the thread pool as every other route does.
"""

from __future__ import annotations

import logging
from typing import Annotated, Final

from fastapi import Depends, Request

from app.domain.damage_photo import (
    ACCEPTED_CONTENT_TYPES,
    MAXIMUM_PHOTO_BYTES,
    UNSUPPORTED_PHOTO_MESSAGE,
    ensure_photo_size,
)
from app.domain.errors import UnsupportedPhoto

logger = logging.getLogger(__name__)

CONTENT_TYPE_HEADER: Final[str] = "content-type"
CONTENT_LENGTH_HEADER: Final[str] = "content-length"
PARAMETER_SEPARATOR: Final[str] = ";"

# What the contract says the body of an upload is.
PHOTO_REQUEST_BODY: Final[dict[str, object]] = {
    "requestBody": {
        "required": True,
        "description": (
            f"The photograph itself, at most {MAXIMUM_PHOTO_BYTES} bytes. Its first bytes "
            "decide whether it is a JPEG or a PNG."
        ),
        "content": {
            content_type: {"schema": {"type": "string", "format": "binary"}}
            for content_type in sorted(ACCEPTED_CONTENT_TYPES)
        },
    }
}


async def read_photo_body(request: Request) -> bytes:
    """Return the body of an upload, refusing it as soon as it is plainly not a photograph.

    Raises:
        UnsupportedPhoto: If the media type is not image/jpeg or image/png.
        PhotoTooLarge: If the declared or the actual length passes the cap.

    """
    media_type = request.headers.get(CONTENT_TYPE_HEADER, "").split(PARAMETER_SEPARATOR)[0]
    media_type = media_type.strip().lower()
    if media_type not in ACCEPTED_CONTENT_TYPES:
        logger.info("damage_photo.media_type_refused", extra={"media_type": media_type or None})
        raise UnsupportedPhoto(UNSUPPORTED_PHOTO_MESSAGE, {"media_type": media_type or None})
    declared = _declared_length(request)
    if declared is not None:
        ensure_photo_size(declared)
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        ensure_photo_size(len(received))
    logger.debug(
        "damage_photo.body_read",
        extra={"declared_bytes": declared, "received_bytes": len(received)},
    )
    return bytes(received)


def _declared_length(request: Request) -> int | None:
    """Return the length the client declared, or None when it declared none we can read."""
    raw = request.headers.get(CONTENT_LENGTH_HEADER)
    if raw is None or not raw.strip().isdigit():
        return None
    return int(raw.strip())


PhotoBody = Annotated[bytes, Depends(read_photo_body)]
