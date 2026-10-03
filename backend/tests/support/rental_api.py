"""Paths, bodies and helpers for the tests of returns, losses, the balance payment and the lists.

The clock of the booking tests stands still on Monday the second of March 2026
at ten in the morning in Cape Town. `on_hire` books a hire for today at the
counter, confirms it and checks it out, so a test starts from a rental that is
out. The worked example of the design document holds a deposit of R1,200.00
and charges R120.00 a day late, so `worked_example_world` sets the deposit of
the world's model to that before anything is booked, and the booking copies it
(BR-20).

Request bodies are built in the camelCase names the React client posts.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from httpx import Response
from sqlmodel import Session

from app.domain.period import BookingPeriod
from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, build_booking_world
from tests.support.checkout_api import TODAY, checked_out, confirmed_today, rental_path
from tests.support.factories import Factory

MY_RENTALS_PATH: Final[str] = "/api/me/rentals"
RENTALS_LIST_PATH: Final[str] = "/api/rentals"
WORKED_EXAMPLE_DEPOSIT: Final[Decimal] = Decimal("1200.00")
CONDITION_IN: Final[str] = "A"
ONE_DAY: Final[timedelta] = timedelta(days=1)
# The hire of the tests here, from today to the sixth, which is the day it is due back.
TODAY_TO_THE_SIXTH: Final[BookingPeriod] = BookingPeriod(TODAY, date(2026, 3, 6))


def worked_example_world(session: Session, factory: Factory, units: int = 1) -> BookingWorld:
    """Return a committed world whose model holds a deposit of R1,200.00 and R120.00 a day late."""
    world = build_booking_world(factory, asset_count=units)
    world.product_model.deposit_amount = WORKED_EXAMPLE_DEPOSIT
    session.add(world.product_model)
    session.commit()
    return world


def on_hire(
    booking: BookingClient,
    world: BookingWorld,
    staff: UserAccount,
    *,
    quantity: int = 1,
    period: BookingPeriod = TODAY_TO_THE_SIXTH,
) -> dict[str, object]:
    """Book a hire for today at the counter, confirm it, check it out, and return the rental."""
    reservation = confirmed_today(booking, world, staff, quantity=quantity, period=period)
    return checked_out(booking, staff, reservation["id"])


def item_ids(rental: dict[str, object]) -> list[str]:
    """Return the keys of the items of a rental, in the order it lists them."""
    items = rental["items"]
    assert isinstance(items, list)
    return [str(item["id"]) for item in items]


def return_body(*item_keys: str, **changes: object) -> dict[str, object]:
    """Return the list the counter posts for the units named, in grade A unless told otherwise."""
    return {
        "items": [
            {
                "rentalItemId": key,
                "conditionIn": CONDITION_IN,
                "hourMeterIn": None,
                "accessoriesIn": None,
                "notes": None,
                "flaggedForDamage": False,
                **changes,
            }
            for key in item_keys
        ]
    }


def take_back(
    booking: BookingClient, account: UserAccount, key: object, body: dict[str, object]
) -> Response:
    """Post a return of a rental as `account`."""
    return booking.client.post(
        f"{rental_path(key)}/returns", json=body, headers=booking.headers(account)
    )


def record_loss(
    booking: BookingClient, account: UserAccount, key: object, item_key: object
) -> Response:
    """Record one unit of a rental as lost, as `account`."""
    return booking.client.post(
        f"{rental_path(key)}/items/{item_key}/loss", headers=booking.headers(account)
    )


def pay_balance(
    booking: BookingClient, account: UserAccount, key: object, reference: object
) -> Response:
    """Record the payment of a rental's balance as `account`."""
    return booking.client.post(
        f"{rental_path(key)}/balance-payment",
        json={"paymentReference": reference},
        headers=booking.headers(account),
    )


def list_rentals(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """List rentals as a member of staff."""
    return booking.client.get(RENTALS_LIST_PATH, params=params, headers=booking.headers(account))


def my_rentals(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """List the caller's own rentals."""
    return booking.client.get(MY_RENTALS_PATH, params=params, headers=booking.headers(account))


def charges_of(rental: dict[str, object], charge_type: str) -> list[dict[str, object]]:
    """Return the charges of one type on a rental, in the order it lists them."""
    charges = rental["charges"]
    assert isinstance(charges, list)
    return [charge for charge in charges if charge["type"] == charge_type]


__all__ = [
    "MY_RENTALS_PATH",
    "ONE_DAY",
    "RENTALS_LIST_PATH",
    "TODAY_TO_THE_SIXTH",
    "WORKED_EXAMPLE_DEPOSIT",
    "charges_of",
    "item_ids",
    "list_rentals",
    "my_rentals",
    "on_hire",
    "pay_balance",
    "record_loss",
    "return_body",
    "take_back",
    "worked_example_world",
]
