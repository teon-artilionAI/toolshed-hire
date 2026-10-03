"""The counter's damage flag is stored in its own column on PostgreSQL (BR-35).

A unit the counter flags at return goes to quarantine and waits for a damage
report, and the flag has to outlive the return for that. It lives in
`rental_item.flagged_for_damage`, the column revision 0006 added. These take a
unit back through HTTP on the real database, in the grade it went out in so
the flag alone decides, and read the committed row on a connection of their
own. The flag is in its column, the notes are exactly what the counter posted,
and a later read of the rental still says the unit waits for its assessment.

The hire goes out on Monday the second of March 2026 and comes back that day.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import RentalItem, UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered
from tests.support.checkout_api import read_rental
from tests.support.damage_api import only_item
from tests.support.factories import Factory
from tests.support.rental_api import (
    item_ids,
    on_hire,
    return_body,
    take_back,
    worked_example_world,
)

pytestmark = pytest.mark.postgres

COUNTER_NOTES: Final[str] = "Guard cracked near the hinge. The customer says it was dropped."


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


def returned_as_it_went_out(
    booking: BookingClient, world: BookingWorld, staff: UserAccount, **changes: object
) -> dict[str, object]:
    """Put one unit out today, take it back in the grade it went out in, and read the rental."""
    rental = on_hire(booking, world, staff)
    body = return_body(*item_ids(rental), **changes)
    answered(take_back(booking, staff, rental["id"], body))
    return answered(read_rental(booking, staff, rental["id"]))


def stored_flag_and_notes(engine: Engine, item_id: object) -> tuple[bool, str | None]:
    """Return the committed flag and notes of one rental item, read on a connection of its own."""
    with Session(engine) as reader:
        row = reader.get(RentalItem, UUID(str(item_id)))
        assert row is not None, f"Rental item {item_id} was not committed."
        return row.flagged_for_damage, row.notes


class TestTheFlagIsStoredInItsColumn:
    """The return writes the flag to its column and leaves the notes as the counter wrote them."""

    def test_a_flagged_return_writes_the_column_and_leaves_the_notes_untouched(
        self,
        postgres_engine: Engine,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        hire = returned_as_it_went_out(
            booking, world, assistant, notes=COUNTER_NOTES, flaggedForDamage=True
        )
        item = only_item(hire)
        assert stored_flag_and_notes(postgres_engine, item["id"]) == (True, COUNTER_NOTES)
        assert (item["conditionIn"], item["damageAssessment"]) == ("A", "REQUIRED")
        assert hire["settlementWaitingOn"] == "DAMAGE_ASSESSMENT"

    def test_a_return_that_is_not_flagged_stores_false_and_waits_for_nothing(
        self,
        postgres_engine: Engine,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        hire = returned_as_it_went_out(booking, world, assistant, notes=COUNTER_NOTES)
        item = only_item(hire)
        assert stored_flag_and_notes(postgres_engine, item["id"]) == (False, COUNTER_NOTES)
        assert item["damageAssessment"] == "NOT_NEEDED"
