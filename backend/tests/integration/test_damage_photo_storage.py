"""Damage photographs on PostgreSQL itself (#83, #112).

The table holds what the migration says. The object key is unique, the media
type is one of the two a photograph is stored as, and the report's photographs
are reached through their own index. Two photographs sent at once for a report
that holds five are counted in turn under the report's lock, so exactly one of
them is kept and the report ends with six. The customer's read joins the hire
to its owner on the real schema, so another customer reads nothing.

The hire goes out on Monday the second of March 2026 and comes back the same
day a grade worse.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Final
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.application.hire.damage_models import DamageReportKey
from app.application.hire.upload_damage_photo import (
    UploadDamagePhotoCommand,
    UploadDamagePhotoUseCase,
)
from app.application.ownership import OwnerScope
from app.domain.enums import UserRole
from app.domain.errors import PhotoLimitReached
from app.domain.identity import Actor
from app.infrastructure.damage_photos import SqlDamagePhotoRepository
from app.infrastructure.models import DamagePhoto, UserAccount
from app.infrastructure.photo_images import PillowPhotoCleaner
from app.infrastructure.schema_ddl import DAMAGE_PHOTO_REPORT_INDEX, DAMAGE_PHOTO_TABLE
from tests.support.booking import opening
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.memory_photos import MemoryPhotoStore
from tests.support.pg import CHECK_VIOLATION_SQLSTATE, sqlstate_of
from tests.support.photo_api import my_photos, report_on_a_hire, upload
from tests.support.photo_files import jpeg_with_gps, plain_jpeg
from tests.support.rental_api import worked_example_world

pytestmark = pytest.mark.postgres

UNIQUE_VIOLATION_SQLSTATE: Final[str] = "23505"
PHOTOS_ALREADY_HELD: Final[int] = 5
CONTENDERS: Final[int] = 2
WAIT_SECONDS: Final[float] = 15.0


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed world of one unit with the deposit of the worked example."""
    return worked_example_world(postgres_session, postgres_factory)


@pytest.fixture
def assistant(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return account


@pytest.fixture
def report(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> tuple[dict[str, object], dict[str, object]]:
    """Return the customer's hire and the report filed against its unit."""
    return report_on_a_hire(booking, world, assistant)


def insert_photo(engine: Engine, report_id: object, uploader: UUID, **changes: object) -> None:
    """Insert one photograph row by hand, as the owner of the tables, and commit it."""
    values: dict[str, object] = {
        "id": uuid4(),
        "damage_report_id": report_id,
        "object_key": f"damage/{report_id}/{uuid4()}.jpg",
        "content_type": "image/jpeg",
        "size_bytes": 1024,
        "uploaded_by_user_id": uploader,
        **changes,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO damage_photo (id, damage_report_id, object_key, content_type, "
                "size_bytes, uploaded_by_user_id, uploaded_at) VALUES (:id, :damage_report_id, "
                ":object_key, :content_type, :size_bytes, :uploaded_by_user_id, now())"
            ),
            values,
        )


class TestTheTable:
    """What the migration created, checked against the catalogue."""

    def test_the_photographs_of_a_report_are_reached_through_their_own_index(
        self, postgres_session: Session
    ) -> None:
        definition = postgres_session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = :table AND indexname = :name"),
            {"table": DAMAGE_PHOTO_TABLE, "name": DAMAGE_PHOTO_REPORT_INDEX},
        ).scalar_one()
        assert "(damage_report_id)" in definition

    def test_two_rows_cannot_name_one_object(
        self,
        postgres_engine: Engine,
        report: tuple[dict[str, object], dict[str, object]],
        assistant: UserAccount,
    ) -> None:
        _, filed = report
        key = f"damage/{filed['id']}/{uuid4()}.jpg"
        insert_photo(postgres_engine, filed["id"], assistant.id, object_key=key)
        with pytest.raises(IntegrityError) as refused:
            insert_photo(postgres_engine, filed["id"], assistant.id, object_key=key)
        assert sqlstate_of(refused.value) == UNIQUE_VIOLATION_SQLSTATE

    @pytest.mark.parametrize("media_type", ["image/svg+xml", "image/gif", "text/html"])
    def test_a_media_type_a_photograph_is_never_stored_as_is_refused(
        self,
        postgres_engine: Engine,
        report: tuple[dict[str, object], dict[str, object]],
        assistant: UserAccount,
        media_type: str,
    ) -> None:
        _, filed = report
        with pytest.raises(IntegrityError) as refused:
            insert_photo(postgres_engine, filed["id"], assistant.id, content_type=media_type)
        assert sqlstate_of(refused.value) == CHECK_VIOLATION_SQLSTATE


class TestTwoPhotographsForTheLastPlace:
    """The report's lock makes the second wait and count the first."""

    def test_exactly_one_is_kept_and_the_report_ends_with_six(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        report: tuple[dict[str, object], dict[str, object]],
        assistant: UserAccount,
    ) -> None:
        _, filed = report
        for _ in range(PHOTOS_ALREADY_HELD):
            insert_photo(postgres_engine, filed["id"], assistant.id)
        both_stored = threading.Barrier(CONTENDERS, timeout=WAIT_SECONDS)
        store = StoreThatWaitsForBoth(both_stored)
        actor = Actor(user_id=assistant.id, role=assistant.role, branch_id=assistant.branch_id)

        def attach() -> str:
            """Attach one photograph on a connection of its own, and say how it ended."""
            use_case = UploadDamagePhotoUseCase(
                opening(postgres_engine)(), FixedClock(), store, PillowPhotoCleaner()
            )
            try:
                use_case.execute(
                    UploadDamagePhotoCommand(
                        actor=actor,
                        key=DamageReportKey.parse(str(filed["id"])),
                        content=plain_jpeg(),
                    )
                )
            except PhotoLimitReached:
                return "refused"
            return "kept"

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            outcomes = sorted(pool.map(lambda _: attach(), range(CONTENDERS)))

        assert outcomes == ["kept", "refused"]
        rows = postgres_session.exec(
            select(DamagePhoto).where(col(DamagePhoto.damage_report_id) == filed["id"])
        ).all()
        assert len(rows) == PHOTOS_ALREADY_HELD + 1
        assert len(store.objects) == CONTENDERS


class StoreThatWaitsForBoth(MemoryPhotoStore):
    """An in memory bucket whose upload waits until both contenders have reached it.

    Both have passed the first count by then, so the second count, under the
    report's lock, is the only thing that can tell them apart.
    """

    def __init__(self, barrier: threading.Barrier) -> None:
        """Keep the barrier both uploads meet at."""
        super().__init__()
        self._barrier = barrier
        self._lock = threading.Lock()

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        """Wait for the other contender, then keep the object."""
        self._barrier.wait()
        with self._lock:
            super().put(object_key, content, content_type)


class TestTheCustomersRead:
    """The hire is joined to its owner on the real schema."""

    def test_the_owner_reads_the_photographs_and_another_customer_reads_nothing(
        self,
        booking: BookingClient,
        postgres_session: Session,
        postgres_factory: Factory,
        world: BookingWorld,
        assistant: UserAccount,
        report: tuple[dict[str, object], dict[str, object]],
    ) -> None:
        rental, filed = report
        photo = created(upload(booking, assistant, filed["id"], jpeg_with_gps()))
        stranger = postgres_factory.user(role=UserRole.CUSTOMER)
        postgres_factory.customer_profile(branch=world.branch, account=stranger)
        postgres_session.commit()

        listed = answered(my_photos(booking, world.customer, rental["id"]))
        refused = my_photos(booking, stranger, rental["id"])

        assert [item["id"] for item in listed["items"]] == [photo["id"]]
        assert refused.status_code == 404, refused.text
        photos = SqlDamagePhotoRepository(postgres_session)
        rental_id = UUID(str(rental["id"]))
        assert photos.rental_is_visible(rental_id, OwnerScope(world.customer.id))
        assert not photos.rental_is_visible(rental_id, OwnerScope(stranger.id))
        assert photos.of_rental(rental_id, OwnerScope(stranger.id)) == ()
        assert len(photos.of_rental(rental_id, OwnerScope(None))) == 1
