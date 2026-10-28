"""Attaching photographs to a damage report and reading them back, through HTTP (#83).

The counter sends a photograph as the raw body. It is checked by its first
bytes, re-encoded with nothing but its pixels, and stored under a random name in
the bucket, which is the in memory store of the `photo_store` fixture here.
Staff read a report's photographs and a five minute link to each, and a
customer is refused by role. These run against the in memory database on a
clock that stands still on Monday the second of March 2026.

The refusals of the upload, and the state with photographs switched off, are in
tests/api/test_damage_photo_refusals.py. The customer's own reads are in
tests/api/test_my_damage_photos.py.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from sqlmodel import Session, col, select

from app.domain.damage_photo import PHOTO_LINK_LIFETIME
from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, DamagePhoto, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.factories import Factory
from tests.support.memory_photos import STORAGE_ORIGIN, TEST_BUCKET, MemoryPhotoStore
from tests.support.photo_api import (
    PHOTO_MEMBERS,
    PNG_TYPE,
    list_photos,
    photo_link,
    report_on_a_hire,
    upload,
)
from tests.support.photo_files import (
    CAMERA_MODEL,
    HEIGHT,
    ROTATED_ORIENTATION,
    WIDTH,
    jpeg_with_gps,
    metadata_of,
    mode_of,
    png_with_gps,
    size_of,
)
from tests.support.rental_api import worked_example_world

OBJECT_KEY: Final[re.Pattern[str]] = re.compile(
    r"^damage/[0-9a-f-]{36}/[0-9a-f-]{36}\.(jpg|png)$"
)
JPEG_FILE_NAME: Final[re.Pattern[str]] = re.compile(
    r'^attachment; filename="TSH-D-26-\d{5}-[0-9a-f]{8}\.jpg"$'
)
TWO_UNITS: Final[int] = 2


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units with the deposit of the worked example."""
    return worked_example_world(session, factory, units=TWO_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator, who acts at every branch."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def report(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> dict[str, object]:
    """Return a report filed against the world's unit as it came back from a hire."""
    _, filed = report_on_a_hire(booking, world, assistant)
    return filed


class TestAttachingAPhotograph:
    """The photograph is kept without its metadata, under a name nobody can guess."""

    def test_a_jpeg_is_stored_upright_with_no_gps_and_no_camera(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        photo_store: MemoryPhotoStore,
    ) -> None:
        sent = jpeg_with_gps(orientation=ROTATED_ORIENTATION)
        assert "gps" in metadata_of(sent)

        photo = created(upload(booking, assistant, report["id"], sent))

        assert set(photo) == PHOTO_MEMBERS
        assert (photo["damageReportId"], photo["damageReportReference"]) == (
            report["id"], report["reference"]
        )
        assert photo["contentType"] == "image/jpeg"
        key, stored = photo_store.only_object()
        assert OBJECT_KEY.match(key) and key.startswith(f"damage/{report['id']}/")
        assert str(photo["id"]) in key
        assert stored.content_type == "image/jpeg"
        assert photo["sizeBytes"] == len(stored.content)
        left = metadata_of(stored.content)
        assert "gps" not in left and "exif" not in left and "comment" not in left
        assert CAMERA_MODEL.encode() not in stored.content
        assert size_of(stored.content) == (HEIGHT, WIDTH)

    def test_a_png_carrying_exif_gps_and_a_text_chunk_keeps_neither(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        photo_store: MemoryPhotoStore,
    ) -> None:
        sent = png_with_gps(transparent=True)
        assert {"gps", "text"} <= set(metadata_of(sent))

        photo = created(upload(booking, assistant, report["id"], sent, PNG_TYPE))

        _, stored = photo_store.only_object()
        assert photo["contentType"] == stored.content_type == "image/png"
        assert metadata_of(stored.content) == {}
        assert mode_of(stored.content) == "RGBA"

    def test_the_format_follows_the_bytes_and_not_the_declared_type(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        photo_store: MemoryPhotoStore,
    ) -> None:
        photo = created(upload(booking, assistant, report["id"], png_with_gps(), "image/jpeg"))
        key, stored = photo_store.only_object()
        assert photo["contentType"] == stored.content_type == "image/png"
        assert key.endswith(".png")

    def test_a_report_is_named_by_its_reference_as_well(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        photo = created(upload(booking, assistant, report["reference"], jpeg_with_gps()))
        assert photo["damageReportId"] == report["id"]

    def test_an_administrator_attaches_one_at_any_branch(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        report: dict[str, object],
    ) -> None:
        created(upload(booking, administrator, report["id"], jpeg_with_gps()))

    def test_the_sixth_is_accepted(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        for _ in range(6):
            created(upload(booking, assistant, report["id"], jpeg_with_gps()))
        assert len(answered(list_photos(booking, assistant, report["id"]))["items"]) == 6

    def test_the_photograph_is_recorded_and_audited(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        session: Session,
    ) -> None:
        photo = created(upload(booking, assistant, report["id"], jpeg_with_gps()))

        row = session.exec(select(DamagePhoto)).one()
        assert (str(row.id), row.uploaded_by_user_id) == (photo["id"], assistant.id)
        event = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == "damage_report.photo_added")
        ).one()
        assert str(event.entity_id) == report["id"]
        assert event.actor_user_id == assistant.id
        assert event.before_state == {"photo_count": 0}
        assert event.after_state is not None
        assert event.after_state["photo_count"] == 1
        assert event.after_state["damage_photo_id"] == photo["id"]


class TestReadingThePhotographs:
    """Staff list a report's photographs and open each through a five minute link."""

    def test_the_list_is_oldest_first_and_names_no_object(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        administrator: UserAccount,
        report: dict[str, object],
    ) -> None:
        first = created(upload(booking, assistant, report["id"], jpeg_with_gps()))
        booking.clock.advance(timedelta(minutes=1))
        second = created(upload(booking, assistant, report["id"], png_with_gps(), PNG_TYPE))

        listed = answered(list_photos(booking, administrator, report["id"]))

        assert [item["id"] for item in listed["items"]] == [first["id"], second["id"]]
        assert all(set(item) == PHOTO_MEMBERS for item in listed["items"])

    def test_a_report_with_no_photographs_lists_none(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        assert answered(list_photos(booking, assistant, report["id"])) == {"items": []}

    def test_the_link_works_for_five_minutes_and_is_served_as_a_download(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        administrator: UserAccount,
        report: dict[str, object],
        photo_store: MemoryPhotoStore,
    ) -> None:
        photo = created(upload(booking, assistant, report["id"], jpeg_with_gps()))

        link = answered(photo_link(booking, administrator, report["id"], photo["id"]))

        assert set(link) == {"url", "expiresAt"}
        expires_at = datetime.fromisoformat(str(link["expiresAt"]))
        assert expires_at - booking.clock.now() == PHOTO_LINK_LIFETIME == timedelta(minutes=5)
        url = urlsplit(str(link["url"]))
        assert f"{url.scheme}://{url.netloc}" == STORAGE_ORIGIN
        assert url.path.startswith(f"/{TEST_BUCKET}/damage/{report['id']}/")
        query = parse_qs(url.query)
        assert query["X-Goog-Expires"] == ["300"]
        assert JPEG_FILE_NAME.match(unquote(query["response-content-disposition"][0]))
        (asked,) = photo_store.links
        assert asked.lifetime == PHOTO_LINK_LIFETIME

    def test_a_photograph_of_another_report_is_not_found_on_this_one(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        report: dict[str, object],
    ) -> None:
        photo = created(upload(booking, assistant, report["id"], jpeg_with_gps()))
        _, other = report_on_a_hire(booking, world, assistant)

        response = photo_link(booking, assistant, other["id"], photo["id"])

        assert response.status_code == 404, response.text
        assert answered(photo_link(booking, assistant, report["id"], photo["id"]))["url"]
