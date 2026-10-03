"""Paths, bodies and a few helpers for the tests of checkout, the rental and the customers.

The clock of the booking tests stands still on Monday the second of March
2026. A hire that starts that day can be checked out at once, which is what
`TODAY_HIRE` is for. Staff may book for today, so a counter booking for it is
the ordinary case. A hire that starts later is checked out by moving the clock
to its first day.

`confirmed_today` books, holds and confirms a reservation for today through
the routes themselves, the way the counter would, and `checkout_body` builds
the list the counter posts from what the checkout read returned.

Request bodies are built in the camelCase names the React client posts.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from httpx import Response

from app.domain.period import BookingPeriod
from app.infrastructure.models import UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    created,
    reservation_path,
)

CUSTOMERS_PATH: Final[str] = "/api/customers"
RENTALS_PATH: Final[str] = "/api/rentals"

# The members the contract gives a rental, one of its items, one of its
# charges and the checkout read, and nothing else.
RENTAL_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "reference", "status", "reservationId", "reservationReference", "branchCode",
        "branchName", "customerProfileId", "customerName", "customerPhone", "from", "dueBackOn",
        "checkedOutAt", "returnedAt", "items", "charges", "depositHeld", "depositWithheld",
        "depositRefunded", "balanceDue", "settledAt", "agreementSigned", "canReturn",
        "settlementWaitingOn",
    }
)  # fmt: skip
ITEM_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "assetTag", "modelName", "modelSlug", "conditionOut", "conditionIn", "hourMeterOut",
        "hourMeterIn", "accessoriesOut", "accessoriesIn", "returnedAt", "daysLate",
        "lateFeePerDay", "daysLateToday", "lateFeeToday", "damageAssessment", "replacementValue",
    }
)  # fmt: skip
CHARGE_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "type", "description", "amountExVat", "vatRate", "vatAmount", "amountIncVat",
        "status", "raisedAt", "rentalItemId",
    }
)  # fmt: skip
CHECKOUT_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "reservationId", "reference", "status", "branchCode", "branchName", "customer", "from",
        "to", "hireDays", "units", "hireTotalIncVat", "depositTotal", "canCheckOut", "refusal",
        "rentalId",
    }
)  # fmt: skip
# The business day of the still clock.
TODAY: Final[date] = date(2026, 3, 2)
TODAY_HIRE: Final[BookingPeriod] = BookingPeriod(TODAY, date(2026, 3, 5))
CONDITION_OUT: Final[str] = "A"
DEFAULT_QUANTITY: Final[int] = 1


def checkout_path(key: object) -> str:
    """Return the path of the checkout of one reservation, by its key or its reference."""
    return f"{reservation_path(key)}/checkout"


def rental_path(key: object) -> str:
    """Return the path of one rental, by its key or its reference."""
    return f"{RENTALS_PATH}/{key}"


def customer_path(key: object) -> str:
    """Return the path of one customer, by its key."""
    return f"{CUSTOMERS_PATH}/{key}"


def confirmed_today(
    booking: BookingClient,
    world: BookingWorld,
    staff: UserAccount,
    *,
    quantity: int = DEFAULT_QUANTITY,
    period: BookingPeriod = TODAY_HIRE,
) -> dict[str, object]:
    """Book, hold and confirm a reservation for the world's customer, as a member of staff.

    Args:
        booking: The reservation routes on the still clock.
        world: The branch, the model and the customer.
        staff: The counter assistant or administrator at the counter.
        quantity: How many units of the world's model.
        period: The hire. Today's, unless the test wants another.

    Returns:
        The reservation, now CONFIRMED.

    """
    draft = created(
        booking.create(
            staff, world.payload(period, quantity=quantity, customer_profile_id=world.profile.id)
        )
    )
    answered(booking.hold(staff, draft["id"]))
    return answered(booking.confirm(staff, draft["id"]))


def read_checkout(booking: BookingClient, account: UserAccount, key: object) -> Response:
    """Read the checkout of a reservation as `account`."""
    return booking.client.get(checkout_path(key), headers=booking.headers(account))


def check_out(
    booking: BookingClient, account: UserAccount, key: object, body: dict[str, object]
) -> Response:
    """Post the checkout of a reservation as `account`."""
    return booking.client.post(checkout_path(key), json=body, headers=booking.headers(account))


def read_rental(booking: BookingClient, account: UserAccount, key: object) -> Response:
    """Read one rental as `account`."""
    return booking.client.get(rental_path(key), headers=booking.headers(account))


def checkout_body(
    preview: dict[str, object], *, agreement_signed: bool = True, **item_changes: object
) -> dict[str, object]:
    """Return the list the counter posts for every unit a checkout read returned.

    Args:
        preview: The body of the checkout read.
        agreement_signed: Whether the customer signed the agreement.
        item_changes: Members to set on every item, for example `hourMeterOut`.

    """
    units = preview["units"]
    assert isinstance(units, list), "The checkout read returned no list of units."
    return {
        "items": [
            {
                "allocationId": unit["allocationId"],
                "conditionOut": CONDITION_OUT,
                "accessoriesOut": None,
                "hourMeterOut": None,
                **item_changes,
            }
            for unit in units
        ],
        "agreementSigned": agreement_signed,
    }


def checked_out(
    booking: BookingClient, staff: UserAccount, key: object
) -> dict[str, object]:
    """Read the checkout of a reservation and post it in full, and return the rental."""
    preview = answered(read_checkout(booking, staff, key))
    return created(check_out(booking, staff, key, checkout_body(preview)))


__all__ = [
    "CHARGE_MEMBERS",
    "CHECKOUT_MEMBERS",
    "CUSTOMERS_PATH",
    "ITEM_MEMBERS",
    "RENTALS_PATH",
    "RENTAL_MEMBERS",
    "TODAY",
    "TODAY_HIRE",
    "check_out",
    "checked_out",
    "checkout_body",
    "checkout_path",
    "confirmed_today",
    "customer_path",
    "read_checkout",
    "read_rental",
    "rental_path",
]
