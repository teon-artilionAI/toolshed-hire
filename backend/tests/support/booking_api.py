"""A world, a client and a few helpers for the tests of the reservation routes.

`build_booking_world` creates what a reservation needs before there is one,
which is a branch, a published model with its units, and a customer who has an
account, a profile and a verified address. It is the database counterpart of
the in memory world in `memory_world`.

`BookingClient` drives the six reservation routes as a chosen account, on a
clock that stands still. A token is minted at the instant the clock shows,
because the application reads the same clock when it checks one. It works on
the in memory database and on PostgreSQL alike, because the only thing that
differs between the two is the session behind the client it is handed.

Request bodies are built in the camelCase names the React client posts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app.domain.enums import AccountStatus, ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    Asset,
    Branch,
    CustomerProfile,
    ProductModel,
    Reservation,
    UserAccount,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.tokens import authorization_header, mint_access_token

logger = logging.getLogger(__name__)

RESERVATIONS_PATH: Final[str] = "/api/reservations"
SINGLE_ASSET: Final[int] = 1
DEFAULT_QUANTITY: Final[int] = 1
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
# The worked example hire, which is inside the booking window of the fixed clock.
FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
# When the seeded customer of a world proved their address.
VERIFIED_AT: Final[datetime] = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def reservation_path(key: object) -> str:
    """Return the path of one reservation, by its key or its reference."""
    return f"{RESERVATIONS_PATH}/{key}"


def hold_path(key: object) -> str:
    """Return the path that puts a reservation on hold."""
    return f"{reservation_path(key)}/hold"


def confirm_path(key: object) -> str:
    """Return the path that confirms a reservation."""
    return f"{reservation_path(key)}/confirm"


def cancellation_path(key: object) -> str:
    """Return the path that cancels a reservation."""
    return f"{reservation_path(key)}/cancellation"


@dataclass(frozen=True, slots=True)
class BookingWorld:
    """One branch, one published model with its units, and a customer who can book."""

    branch: Branch
    product_model: ProductModel
    assets: list[Asset]
    customer: UserAccount
    profile: CustomerProfile

    def payload(
        self,
        period: BookingPeriod = FIRST_HIRE,
        *,
        quantity: int = DEFAULT_QUANTITY,
        customer_profile_id: UUID | None = None,
    ) -> dict[str, object]:
        """Return the body that asks for a draft of this world's model at its branch."""
        body: dict[str, object] = {
            "branchCode": self.branch.code,
            "from": period.start.isoformat(),
            "to": period.end.isoformat(),
            "lines": [{"modelSlug": self.product_model.slug, "quantity": quantity}],
        }
        if customer_profile_id is not None:
            body["customerProfileId"] = str(customer_profile_id)
        return body


def build_booking_world(
    factory: Factory,
    *,
    asset_count: int = SINGLE_ASSET,
    email_verified: bool = True,
    account_status: AccountStatus = AccountStatus.ACTIVE,
    trade_discount_percent: Decimal | None = None,
) -> BookingWorld:
    """Create a branch, a published model, its units and a customer with a profile.

    Nothing is committed. The test owns the commit, which matters because a
    request only sees what was committed before it.

    Args:
        factory: The factory bound to the session under test.
        asset_count: How many interchangeable units the branch holds.
        email_verified: Whether the customer has proved their address.
        account_status: The standing of the customer.
        trade_discount_percent: The trade discount on the profile, when there is one.

    """
    branch = factory.branch()
    model = factory.product_model()
    assets = [factory.asset(product_model=model, branch=branch) for _ in range(asset_count)]
    customer = factory.user(role=UserRole.CUSTOMER)
    customer.email_verified_at = VERIFIED_AT if email_verified else None
    profile = factory.customer_profile(branch=branch, account=customer)
    profile.account_status = account_status
    if trade_discount_percent is not None:
        profile.trade_discount_percent = trade_discount_percent
    factory.session.add(customer)
    factory.session.add(profile)
    factory.session.flush()
    logger.debug(
        "test.booking_world_built",
        extra={"branch_code": branch.code, "sku": model.sku, "asset_count": len(assets)},
    )
    return BookingWorld(
        branch=branch, product_model=model, assets=assets, customer=customer, profile=profile
    )


@dataclass(frozen=True, slots=True)
class BookingClient:
    """The six reservation routes, driven as a chosen account on a still clock."""

    client: TestClient
    clock: FixedClock

    def headers(self, account: UserAccount, request_id: str | None = None) -> dict[str, str]:
        """Return the request headers of a signed in account."""
        headers = authorization_header(
            mint_access_token(account.id, role=account.role, issued_at=self.clock.now())
        )
        if request_id is not None:
            headers[REQUEST_ID_HEADER] = request_id
        return headers

    def create(
        self, account: UserAccount, body: dict[str, object], request_id: str | None = None
    ) -> Response:
        """Post a draft as `account`."""
        return self.client.post(
            RESERVATIONS_PATH, json=body, headers=self.headers(account, request_id)
        )

    def hold(self, account: UserAccount, key: object, request_id: str | None = None) -> Response:
        """Put a reservation on hold as `account`."""
        return self.client.post(hold_path(key), headers=self.headers(account, request_id))

    def confirm(
        self, account: UserAccount, key: object, request_id: str | None = None
    ) -> Response:
        """Confirm a reservation as `account`."""
        return self.client.post(confirm_path(key), headers=self.headers(account, request_id))

    def cancel(self, account: UserAccount, key: object, reason: str | None = None) -> Response:
        """Cancel a reservation as `account`."""
        return self.client.post(
            cancellation_path(key), json={"reason": reason}, headers=self.headers(account)
        )

    def read(self, account: UserAccount, key: object) -> Response:
        """Read one reservation as `account`."""
        return self.client.get(reservation_path(key), headers=self.headers(account))

    def listing(self, account: UserAccount, **params: object) -> Response:
        """List reservations as `account`."""
        return self.client.get(RESERVATIONS_PATH, params=params, headers=self.headers(account))

    def drafted(
        self,
        world: BookingWorld,
        period: BookingPeriod = FIRST_HIRE,
        *,
        quantity: int = DEFAULT_QUANTITY,
    ) -> dict[str, object]:
        """Create a draft as the world's customer, and return the reservation."""
        return created(self.create(world.customer, world.payload(period, quantity=quantity)))

    def held(
        self,
        world: BookingWorld,
        period: BookingPeriod = FIRST_HIRE,
        *,
        quantity: int = DEFAULT_QUANTITY,
    ) -> dict[str, object]:
        """Create a draft and put it on hold as the world's customer."""
        draft = self.drafted(world, period, quantity=quantity)
        return answered(self.hold(world.customer, draft["id"]))

    def confirmed(
        self,
        world: BookingWorld,
        period: BookingPeriod = FIRST_HIRE,
        *,
        quantity: int = DEFAULT_QUANTITY,
    ) -> dict[str, object]:
        """Create a draft, hold it and confirm it as the world's customer."""
        held = self.held(world, period, quantity=quantity)
        return answered(self.confirm(world.customer, held["id"]))


def created(response: Response) -> dict[str, object]:
    """Return the body of a 201, failing with the response when it is anything else."""
    assert response.status_code == status.HTTP_201_CREATED, response.text
    body: dict[str, object] = response.json()
    return body


def answered(response: Response) -> dict[str, object]:
    """Return the body of a 200, failing with the response when it is anything else."""
    assert response.status_code == status.HTTP_200_OK, response.text
    body: dict[str, object] = response.json()
    return body


def force_status(session: Session, reservation_id: object, forced: ReservationStatus) -> None:
    """Put a stored reservation in a status no route can reach yet, and commit it.

    Collection, return and the no-show sweep are later changes, so a test that
    needs a reservation in one of those statuses writes it directly.
    """
    row = session.get(Reservation, UUID(str(reservation_id)))
    assert row is not None, f"No reservation has the key {reservation_id}."
    row.status = forced
    row.hold_expires_at = None
    session.add(row)
    session.commit()


__all__ = [
    "FIRST_HIRE",
    "RESERVATIONS_PATH",
    "BookingClient",
    "BookingWorld",
    "answered",
    "build_booking_world",
    "cancellation_path",
    "confirm_path",
    "created",
    "force_status",
    "hold_path",
    "reservation_path",
]
