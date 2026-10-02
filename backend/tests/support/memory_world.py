"""The smallest in memory world a booking can happen in.

One branch, one product model, a few tagged units and one customer with an
account. It is the in memory counterpart of `scenarios`, which builds the same
world out of database rows. A use case test starts from here so that it is
about the rule it is named after and not about setting up a catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.application.booking.create_reservation import (
    CreateReservationCommand,
    CreateReservationUseCase,
)
from app.application.clock import Clock
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.ports import NotificationGateway
from app.domain.catalogue import Asset, ProductModel
from app.domain.enums import AccountStatus, AssetStatus, ConditionGrade, UserRole
from app.domain.identity import Actor, Branch, CustomerProfile
from app.domain.period import BookingPeriod
from app.infrastructure.notification import FakeEmailGateway
from tests.support.clock import FixedClock
from tests.support.memory import InMemoryUnitOfWork, MemoryStore

SINGLE_ASSET: Final[int] = 1
DEFAULT_QUANTITY: Final[int] = 1
CUSTOMER_EMAIL: Final[str] = "nomsa.dlamini@example.co.za"
DAILY_RATE: Final[Decimal] = Decimal("185.00")
WEEKLY_RATE: Final[Decimal] = Decimal("740.00")
DEPOSIT: Final[Decimal] = Decimal("600.00")
LATE_FEE: Final[Decimal] = Decimal("120.00")
REPLACEMENT_VALUE: Final[Decimal] = Decimal("4200.00")


@dataclass(frozen=True, slots=True)
class MemoryWorld:
    """A store holding one bookable product model, and the keys a test needs."""

    store: MemoryStore
    branch: Branch
    product_model: ProductModel
    assets: list[Asset]
    customer_account_id: UUID
    profile: CustomerProfile

    def command(
        self,
        period: BookingPeriod,
        *,
        quantity: int = DEFAULT_QUANTITY,
        actor: Actor | None = None,
    ) -> CreateReservationCommand:
        """Return the command that books this world's product model for its customer.

        Args:
            period: The hire period to book.
            quantity: How many units.
            actor: Who is making the request. The customer themselves when omitted.

        """
        return CreateReservationCommand(
            actor=actor or Actor(user_id=self.customer_account_id, role=UserRole.CUSTOMER),
            customer_user_id=self.customer_account_id,
            branch_id=self.branch.id,
            product_model_id=self.product_model.id,
            period=period,
            quantity=quantity,
        )


def build_memory_world(
    *, asset_count: int = SINGLE_ASSET, customer_email: str | None = CUSTOMER_EMAIL
) -> MemoryWorld:
    """Create a store with a branch, a product model, its units and a customer.

    Args:
        asset_count: How many interchangeable units the branch holds. They are
            tagged in order, so the first one is the one allocation picks.
        customer_email: The address of the customer's account, or None to
            build a customer a confirmation cannot be sent to.

    """
    branch = Branch(id=uuid4(), code="CBD", name="Cape Town CBD")
    product_model = ProductModel(
        id=uuid4(),
        sku="TSH-PM-0001",
        name="GBH 2-26 DRE Rotary Hammer",
        daily_rate=DAILY_RATE,
        weekly_rate=WEEKLY_RATE,
        deposit_amount=DEPOSIT,
        late_fee_per_day=LATE_FEE,
        replacement_value=REPLACEMENT_VALUE,
    )
    assets = [
        Asset(
            id=uuid4(),
            asset_tag=f"TSH-DR-{number:04d}",
            product_model_id=product_model.id,
            branch_id=branch.id,
            status=AssetStatus.AVAILABLE,
            condition_grade=ConditionGrade.A,
        )
        for number in range(1, asset_count + 1)
    ]
    account_id = uuid4()
    profile = CustomerProfile(
        id=uuid4(),
        user_account_id=account_id,
        display_name="Nomsa Dlamini",
        account_status=AccountStatus.ACTIVE,
        email=customer_email,
    )
    store = MemoryStore(
        branches={branch.id: branch},
        product_models={product_model.id: product_model},
        profiles={account_id: profile},
        assets=list(assets),
    )
    return MemoryWorld(
        store=store,
        branch=branch,
        product_model=product_model,
        assets=assets,
        customer_account_id=account_id,
        profile=profile,
    )


def wire_use_case(
    world: MemoryWorld,
    *,
    gateway: NotificationGateway | None = None,
    clock: Clock | None = None,
) -> CreateReservationUseCase:
    """Return the reservation use case wired to a world, a gateway and a clock.

    The use case and its dispatcher are given a unit of work each over the
    same store, which is how the request wiring behaves once the booking
    transaction has ended and the dispatch begins.

    Args:
        world: The world whose store the booking commits into.
        gateway: The email gateway. A fake that accepts everything when omitted.
        clock: The clock. A fixed clock at its default instant when omitted.

    """
    chosen_clock = clock if clock is not None else FixedClock()
    chosen_gateway = gateway if gateway is not None else FakeEmailGateway()
    dispatcher = NotificationDispatcher(
        InMemoryUnitOfWork(world.store), chosen_gateway, chosen_clock
    )
    return CreateReservationUseCase(InMemoryUnitOfWork(world.store), chosen_clock, dispatcher)


__all__ = ["CUSTOMER_EMAIL", "MemoryWorld", "build_memory_world", "wire_use_case"]
