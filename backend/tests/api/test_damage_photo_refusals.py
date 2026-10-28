"""Everything the photograph routes of a damage report refuse, and the words each refusal uses.

A file is refused for its size before it is read, for its media type, and for
its first bytes, so an SVG renamed to end in .jpg never reaches the decoder. A
seventh photograph is refused with the six kept, and a caller who may not
attach or read one is refused before the body is read. With photographs
switched off every route answers 503 in one plain sentence, and nothing else
about the report changes.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session, select

from app.api.damage_photo_deps import get_photo_store
from app.domain.damage_photo import (
    EMPTY_PHOTO_MESSAGE,
    MAXIMUM_PHOTO_BYTES,
    PHOTO_LIMIT_MESSAGE,
    PHOTO_TOO_LARGE_MESSAGE,
    UNSUPPORTED_PHOTO_MESSAGE,
)
from app.domain.enums import UserRole
from app.infrastructure.models import DamagePhoto, UserAccount
from app.infrastructure.photo_images import TOO_MANY_PIXELS_MESSAGE, UNREADABLE_PHOTO_MESSAGE
from app.infrastructure.photo_store import SwitchedOffPhotoStore
from app.main import app as production_app
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.damage_api import refusal_of
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.memory_photos import MemoryPhotoStore
from tests.support.photo_api import (
    PNG_TYPE,
    list_photos,
    photo_link,
    report_on_a_hire,
    upload,
)
from tests.support.photo_files import (
    SVG_WITH_SCRIPT,
    jpeg_with_gps,
    oversized_jpeg,
    png_claiming_too_many_pixels,
    truncated_jpeg,
)
from tests.support.rental_api import worked_example_world

SWITCHED_OFF: Final[str] = "Photographs are not switched on yet."
NO_SUCH_REPORT: Final[str] = (
    "We could not find that damage report. Check the reference and try again."
)
UNKNOWN_KEY: Final[str] = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of one unit with the deposit of the worked example."""
    return worked_example_world(session, factory)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def report(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> dict[str, object]:
    """Return a report filed against the world's unit as it came back from a hire."""
    _, filed = report_on_a_hire(booking, world, assistant)
    return filed


def photos_kept(session: Session, store: MemoryPhotoStore) -> tuple[int, int]:
    """Return how many photographs the database records and the bucket holds."""
    return len(session.exec(select(DamagePhoto)).all()), len(store.objects)


class TestTheFileItself:
    """Size first, then the media type, then the first bytes, then the decoder."""

    def test_a_renamed_svg_is_refused_by_its_first_bytes(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        session: Session,
        photo_store: MemoryPhotoStore,
    ) -> None:
        response = upload(booking, assistant, report["id"], SVG_WITH_SCRIPT, "image/jpeg")

        assert refusal_of(response, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE) == (
            UNSUPPORTED_PHOTO_MESSAGE
        )
        assert problem_code(response) == "unsupported-photo"
        assert photos_kept(session, photo_store) == (0, 0)

    @pytest.mark.parametrize("media_type", ["image/svg+xml", "text/plain", "image/gif", ""])
    def test_a_body_sent_as_anything_but_jpeg_or_png_is_refused(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        media_type: str,
    ) -> None:
        response = upload(booking, assistant, report["id"], jpeg_with_gps(), media_type)
        assert refusal_of(response, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE) == (
            UNSUPPORTED_PHOTO_MESSAGE
        )

    def test_an_empty_body_is_refused(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        response = upload(booking, assistant, report["id"], b"")
        assert refusal_of(response, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE) == (
            EMPTY_PHOTO_MESSAGE
        )

    def test_a_photograph_one_byte_past_four_megabytes_is_refused(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        session: Session,
        photo_store: MemoryPhotoStore,
    ) -> None:
        response = upload(booking, assistant, report["id"], oversized_jpeg())

        assert refusal_of(response, status.HTTP_413_CONTENT_TOO_LARGE) == PHOTO_TOO_LARGE_MESSAGE
        assert problem_code(response) == "photo-too-large"
        assert photos_kept(session, photo_store) == (0, 0)

    def test_a_declared_length_past_the_cap_is_refused_before_the_body_is_read(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        declared = {"Content-Length": str(MAXIMUM_PHOTO_BYTES + 1)}
        response = upload(
            booking, assistant, report["id"], b"\xff\xd8\xff", extra_headers=declared
        )
        assert refusal_of(response, status.HTTP_413_CONTENT_TOO_LARGE) == PHOTO_TOO_LARGE_MESSAGE

    def test_a_streamed_body_with_no_length_is_cut_off_at_the_cap(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        chunk = b"\xff\xd8\xff" + b"\x00" * (1024 * 1024 - 3)

        def chunks() -> object:
            """Yield five megabytes, one at a time, with no length declared."""
            for _ in range(5):
                yield chunk

        headers = {**booking.headers(assistant), "Content-Type": "image/jpeg"}
        response = booking.client.post(
            f"/api/damage-reports/{report['id']}/photos", content=chunks(), headers=headers
        )
        assert refusal_of(response, status.HTTP_413_CONTENT_TOO_LARGE) == PHOTO_TOO_LARGE_MESSAGE

    def test_a_jpeg_cut_short_is_refused_as_unreadable(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        response = upload(booking, assistant, report["id"], truncated_jpeg())
        assert refusal_of(response, status.HTTP_422_UNPROCESSABLE_CONTENT) == (
            UNREADABLE_PHOTO_MESSAGE
        )

    def test_a_header_claiming_too_many_pixels_is_refused_before_it_is_decoded(
        self, booking: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        claimed = png_claiming_too_many_pixels()
        response = upload(booking, assistant, report["id"], claimed, PNG_TYPE)
        assert refusal_of(response, status.HTTP_422_UNPROCESSABLE_CONTENT) == (
            TOO_MANY_PIXELS_MESSAGE
        )


class TestTheReport:
    """The report has to exist, be within reach and have room."""

    def test_a_seventh_photograph_is_refused_and_the_six_are_kept(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
        session: Session,
        photo_store: MemoryPhotoStore,
    ) -> None:
        for _ in range(6):
            created(upload(booking, assistant, report["id"], jpeg_with_gps()))

        response = upload(booking, assistant, report["id"], jpeg_with_gps())

        assert refusal_of(response, status.HTTP_409_CONFLICT) == PHOTO_LIMIT_MESSAGE
        assert problem_code(response) == "photo-limit-reached"
        assert photos_kept(session, photo_store) == (6, 6)

    def test_an_unknown_report_is_not_found(
        self, booking: BookingClient, assistant: UserAccount
    ) -> None:
        response = upload(booking, assistant, UNKNOWN_KEY, jpeg_with_gps())
        assert refusal_of(response, status.HTTP_404_NOT_FOUND) == NO_SUCH_REPORT

    def test_counter_staff_of_another_branch_are_refused(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        report: dict[str, object],
        photo_store: MemoryPhotoStore,
    ) -> None:
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()

        response = upload(booking, elsewhere, report["id"], jpeg_with_gps())

        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
        assert problem_code(response) == "branch-scope"
        assert photos_kept(session, photo_store) == (0, 0)

    def test_counter_staff_of_another_branch_may_still_read_them(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        assistant: UserAccount,
        report: dict[str, object],
    ) -> None:
        photo = created(upload(booking, assistant, report["id"], jpeg_with_gps()))
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()

        assert len(answered(list_photos(booking, elsewhere, report["id"]))["items"]) == 1
        assert answered(photo_link(booking, elsewhere, report["id"], photo["id"]))["url"]


class TestCallersWhoMayNot:
    """A customer reads the photographs of their own hire elsewhere, and nobody signed out."""

    def test_a_customer_may_not_attach_list_or_open_one(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        report: dict[str, object],
    ) -> None:
        photo = created(upload(booking, assistant, report["id"], jpeg_with_gps()))
        customer = world.customer

        for response in (
            upload(booking, customer, report["id"], jpeg_with_gps()),
            list_photos(booking, customer, report["id"]),
            photo_link(booking, customer, report["id"], photo["id"]),
        ):
            assert response.status_code == status.HTTP_403_FORBIDDEN, response.text

    def test_nobody_signed_out_may_attach_one(
        self, booking: BookingClient, report: dict[str, object]
    ) -> None:
        response = upload(booking, None, report["id"], jpeg_with_gps())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.text


class TestPhotographsSwitchedOff:
    """Without a bucket every photograph route answers 503, and nothing else changes."""

    @pytest.fixture
    def switched_off(self, booking: BookingClient) -> BookingClient:
        """Give the application the store a deployment with no bucket runs with."""
        production_app.dependency_overrides[get_photo_store] = SwitchedOffPhotoStore
        return booking

    def test_every_staff_route_says_photographs_are_off(
        self,
        switched_off: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
    ) -> None:
        for response in (
            upload(switched_off, assistant, report["id"], jpeg_with_gps()),
            list_photos(switched_off, assistant, report["id"]),
            photo_link(switched_off, assistant, report["id"], UNKNOWN_KEY),
        ):
            assert refusal_of(response, status.HTTP_503_SERVICE_UNAVAILABLE) == SWITCHED_OFF
            assert problem_code(response) == "feature-switched-off"

    def test_the_report_itself_still_reads(
        self,
        switched_off: BookingClient,
        assistant: UserAccount,
        report: dict[str, object],
    ) -> None:
        read = answered(
            switched_off.client.get(
                f"/api/damage-reports/{report['id']}", headers=switched_off.headers(assistant)
            )
        )
        assert read["reference"] == report["reference"]

    def test_the_body_is_not_read_before_the_refusal(
        self, switched_off: BookingClient, assistant: UserAccount, report: dict[str, object]
    ) -> None:
        response = upload(switched_off, assistant, report["id"], oversized_jpeg())
        assert refusal_of(response, status.HTTP_503_SERVICE_UNAVAILABLE) == SWITCHED_OFF
