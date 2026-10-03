"""A rental opened at the counter looks like the worked example the seed carries.

The seed writes the worked example of the design document as a closed hire,
rental TSH-H-26-000098. These read it through the rental route, as the counter
would, and then book the same model at the same branch for the same four days
for a seeded customer, check it out, and compare the two. The hire charge and
the deposit hold of the new rental have the figures, the VAT, the status and
the attribution of the worked example's, which is what "shaped like the
worked example" means in practice.

The database is seeded once for the module, and the counter assistant is the
seeded one at CBD. The clock stands still on Monday the second of March 2026.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from typing import Final

import pytest
from sqlmodel import Session, col, select

from app.domain.period import BookingPeriod
from app.infrastructure.models import Branch, CustomerProfile, ProductModel, UserAccount
from seeding.people import CBD_COUNTER_EMAIL, INDIVIDUAL_CUSTOMER_EMAIL
from tests.support.booking_api import BookingClient, answered, created
from tests.support.checkout_api import checked_out, read_rental
from tests.support.clock import FixedClock
from tests.support.sessions import session_client

pytestmark = pytest.mark.postgres

WORKED_EXAMPLE_RENTAL: Final[str] = "TSH-H-26-000098"
WORKED_EXAMPLE_SKU: Final[str] = "DR-BOSCH-GBH226"
# The rental sequence starts after the worked example and is never reset, so a
# new rental is numbered after it, by however many the suite drew before.
RENTAL_REFERENCE: Final[re.Pattern[str]] = re.compile(r"^TSH-H-26-\d{6}$")
FOUR_DAYS_FROM_TODAY: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 2), date(2026, 3, 6))
# The members of a charge that make it the kind of charge it is, as opposed to
# the one hire it was raised on.
CHARGE_SHAPE: Final[tuple[str, ...]] = (
    "type",
    "amountExVat",
    "vatRate",
    "vatAmount",
    "amountIncVat",
    "status",
)


@pytest.fixture
def counter(reader: Session) -> Iterator[BookingClient]:
    """Yield the routes on the seeded database and a still clock."""
    clock = FixedClock()
    with session_client(reader, clock) as client:
        yield BookingClient(client, clock)


@pytest.fixture
def assistant(reader: Session) -> UserAccount:
    """Return the seeded counter assistant of the CBD branch."""
    return reader.exec(select(UserAccount).where(col(UserAccount.email) == CBD_COUNTER_EMAIL)).one()


def worked_example(counter: BookingClient, assistant: UserAccount) -> dict[str, object]:
    """Return the seeded worked example, read through the rental route."""
    return answered(read_rental(counter, assistant, WORKED_EXAMPLE_RENTAL))


def shape_of(charge: object) -> tuple[object, ...]:
    """Return the members of a charge that say what kind of charge it is."""
    assert isinstance(charge, dict)
    return tuple(charge[member] for member in CHARGE_SHAPE)


class TestTheWorkedExampleReadsBack:
    """The closed hire of the design document, as the counter reads it."""

    def test_it_is_settled_with_the_late_fee_taken_from_the_deposit(
        self, counter: BookingClient, assistant: UserAccount
    ) -> None:
        rental = worked_example(counter, assistant)
        assert (rental["status"], rental["settlementWaitingOn"], rental["canReturn"]) == (
            "SETTLED", None, False
        )
        assert (rental["depositHeld"], rental["depositWithheld"]) == ("1200.00", "240.00")
        assert (rental["depositRefunded"], rental["balanceDue"]) == ("960.00", "0.00")
        assert rental["reservationReference"] == "TSH-R-26-000123"

    def test_its_one_unit_came_back_two_days_late(
        self, counter: BookingClient, assistant: UserAccount
    ) -> None:
        (item,) = worked_example(counter, assistant)["items"]
        assert (item["assetTag"], item["daysLate"], item["lateFeePerDay"]) == (
            "TSH-DR-0042", 2, "120.00"
        )
        assert (item["hourMeterOut"], item["hourMeterIn"]) == (401, 412)
        assert (item["daysLateToday"], item["lateFeeToday"]) == (0, "0.00")

    def test_its_four_charges_come_in_the_order_they_were_raised(
        self, counter: BookingClient, assistant: UserAccount
    ) -> None:
        charges = worked_example(counter, assistant)["charges"]
        assert isinstance(charges, list)
        assert [charge["type"] for charge in charges] == [
            "HIRE", "DEPOSIT_HOLD", "LATE_FEE", "DEPOSIT_RELEASE"
        ]


class TestARentalOpenedAtTheCounter:
    """The same model, branch and four days, checked out today."""

    def test_its_two_charges_are_shaped_like_the_worked_examples(
        self, counter: BookingClient, reader: Session, assistant: UserAccount
    ) -> None:
        example = worked_example(counter, assistant)
        model = reader.exec(
            select(ProductModel).where(col(ProductModel.sku) == WORKED_EXAMPLE_SKU)
        ).one()
        branch = reader.exec(select(Branch).where(col(Branch.code) == "CBD")).one()
        customer = reader.exec(
            select(CustomerProfile)
            .join(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
            .where(col(UserAccount.email) == INDIVIDUAL_CUSTOMER_EMAIL)
        ).one()
        body = {
            "branchCode": branch.code,
            "from": FOUR_DAYS_FROM_TODAY.start.isoformat(),
            "to": FOUR_DAYS_FROM_TODAY.end.isoformat(),
            "lines": [{"modelSlug": model.slug, "quantity": 1}],
            "customerProfileId": str(customer.id),
        }
        draft = created(counter.create(assistant, body))
        answered(counter.hold(assistant, draft["id"]))
        answered(counter.confirm(assistant, draft["id"]))

        rental = checked_out(counter, assistant, draft["id"])

        assert RENTAL_REFERENCE.match(str(rental["reference"]))
        assert rental["reference"] > WORKED_EXAMPLE_RENTAL
        example_hire, example_deposit = example["charges"][:2]
        hire, deposit = rental["charges"]
        assert shape_of(hire) == shape_of(example_hire)
        assert shape_of(deposit) == shape_of(example_deposit)
        assert deposit["description"] == example_deposit["description"]
        assert hire["rentalItemId"] == rental["items"][0]["id"]
        assert example_hire["rentalItemId"] == example["items"][0]["id"]
        assert (deposit["rentalItemId"], example_deposit["rentalItemId"]) == (None, None)
