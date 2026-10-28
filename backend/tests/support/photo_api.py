"""Paths and helpers for the tests that attach damage photographs and read them back.

A photograph is posted as the raw body with its media type, as the counter's
browser sends it. `report_with_photo_room` files a report against a unit that
came back a grade worse, so a test starts from a report on a customer's hire.
"""

from __future__ import annotations

from typing import Final

from httpx import Response

from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, created
from tests.support.damage_api import (
    file_report,
    only_item,
    report_body,
    report_path,
    returned_worse,
)

JPEG_TYPE: Final[str] = "image/jpeg"
PNG_TYPE: Final[str] = "image/png"
CONTENT_TYPE_HEADER: Final[str] = "Content-Type"
# The members the contract gives a photograph, and nothing else.
PHOTO_MEMBERS: Final[frozenset[str]] = frozenset(
    {"id", "damageReportId", "damageReportReference", "contentType", "sizeBytes", "uploadedAt"}
)


def photos_path(report_key: object) -> str:
    """Return the path of the photographs of one report."""
    return f"{report_path(report_key)}/photos"


def photo_path(report_key: object, photo_id: object) -> str:
    """Return the path of the link to one photograph of a report."""
    return f"{photos_path(report_key)}/{photo_id}"


def my_photos_path(rental_id: object) -> str:
    """Return the path of the photographs on a customer's own hire."""
    return f"/api/me/rentals/{rental_id}/damage-photos"


def my_photo_path(rental_id: object, photo_id: object) -> str:
    """Return the path of the link to one photograph on a customer's own hire."""
    return f"{my_photos_path(rental_id)}/{photo_id}"


def upload(
    booking: BookingClient,
    account: UserAccount | None,
    report_key: object,
    content: bytes,
    content_type: str = JPEG_TYPE,
    *,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    """Post one photograph to a report as `account`, or as nobody."""
    headers = booking.headers(account) if account is not None else {}
    headers = {**headers, CONTENT_TYPE_HEADER: content_type, **(extra_headers or {})}
    return booking.client.post(photos_path(report_key), content=content, headers=headers)


def list_photos(booking: BookingClient, account: UserAccount, report_key: object) -> Response:
    """List the photographs of a report as `account`."""
    return booking.client.get(photos_path(report_key), headers=booking.headers(account))


def photo_link(
    booking: BookingClient, account: UserAccount, report_key: object, photo_id: object
) -> Response:
    """Ask for the link to one photograph of a report as `account`."""
    return booking.client.get(photo_path(report_key, photo_id), headers=booking.headers(account))


def my_photos(booking: BookingClient, account: UserAccount | None, rental_id: object) -> Response:
    """List the photographs on a hire as `account`, or as nobody."""
    headers = booking.headers(account) if account is not None else {}
    return booking.client.get(my_photos_path(rental_id), headers=headers)


def my_photo_link(
    booking: BookingClient, account: UserAccount | None, rental_id: object, photo_id: object
) -> Response:
    """Ask for the link to one photograph on a hire as `account`, or as nobody."""
    headers = booking.headers(account) if account is not None else {}
    return booking.client.get(my_photo_path(rental_id, photo_id), headers=headers)


def report_on_a_hire(
    booking: BookingClient, world: BookingWorld, staff: UserAccount
) -> tuple[dict[str, object], dict[str, object]]:
    """Put a unit out, take it back worse, file its report, and return the rental and the report."""
    back = returned_worse(booking, world, staff)
    item = only_item(back)
    body = report_body(item["assetTag"], chargeable=False, rental_item_id=item["id"])
    report = created(file_report(booking, staff, body))
    return back, report


__all__ = [
    "JPEG_TYPE",
    "PHOTO_MEMBERS",
    "PNG_TYPE",
    "list_photos",
    "my_photo_link",
    "my_photo_path",
    "my_photos",
    "my_photos_path",
    "photo_link",
    "photo_path",
    "photos_path",
    "report_on_a_hire",
    "upload",
]
