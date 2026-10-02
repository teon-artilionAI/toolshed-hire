"""The smallest in memory world a booking can happen in.

One branch, one product model, a few tagged units and one customer with an
account. It is the in memory counterpart of `scenarios`, which builds the same
world out of database rows. A use case test starts from here so that it is
about the rule it is named after and not about setting up a catalogue.

`open_desk` wires every use case of the booking module over one store, the way
a request wires them. Each use case is given a unit of work of its own, so no
two of them ever share an open transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.application.booking.access import ReservationCommand
from app.application.booking.cancel_reservation import (
    CancelReservationCommand,
    CancelReservationUseCase,
)
from app.application.booking.confirm_reservation import ConfirmReservationUseCase
from app.application.booking.create_reservation import CreateReservationUseCase
from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase
from app.application.booking.hold_reservation import HoldReservationUseCase
from app.application.booking.read_models import ReservationKey
from app.application.booking.read_reservation import ReadReservations
from app.application.booking.reservation_request import (
    CreateReservationCommand,
    RequestedLine,
)
from app.application.booking.views import ReservationView
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.ports import NotificationGateway
from app.domain.booking import Reservation
from app.domain.catalogue import Asset, ProductModel
from app.domain.enums import AccountStatus, AssetStatus, ConditionGrade, UserRole
from app.domain.identity import Actor, Branch, CustomerProfile
from app.domain.period import BookingPeriod
from app.domain.policies import PricingPolicy, StandardPricingPolicy
from app.infrastructure.notification import FakeEmailGateway
from tests.support.clock import FixedClock
from tests.support.memory import InMemoryUnitOfWork, MemoryStore

SINGLE_ASSET: Final[int] = 1
DEFAULT_QUANTITY: Final[int] = 1
CUSTOMER_EMAIL: Final[str] = "nomsa.dlamini@example.co.za"
MODEL_SLUG: Final[str] = "gbh-2-26-dre-rotary-hammer"
DAILY_RATE: Final[Decimal] = Decimal("185.00")
WEEKLY_RATE: Final[Decimal] = Decimal("740.00")
DEPOSIT: Final[Decimal] = Decimal("600.00")
LATE_FEE: Final[Decimal] = Decimal("120.00")
REPLACEMENT_VALUE: Final[Decimal] = Decimal("4200.00")
MIN_HIRE_DAYS: Final[int] = 1
MAX_HIRE_DAYS: Final[int] = 28
NO_DISCOUNT: Final[Decimal] = Decimal("0.00")
# The worked example hire, which is inside the booking window of the fixed clock.
FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))


@dataclass(frozen=True, slots=True)
class MemoryWorld:
    """A store holding one bookable product model, and the keys a test needs."""

    store: MemoryStore
    branch: Branch
    product_model: ProductModel
    assets: list[Asset]
    customer_account_id: UUID
    profile: CustomerProfile

    @property
    def customer(self) -> Actor:
        """Return the customer of this world as the actor of an operation."""
        return Actor(user_id=self.customer_account_id, role=UserRole.CUSTOMER)

    def assistant(self, *, at_own_branch: bool = True) -> Actor:
        """Return a counter assistant, at this world's branch or at another one."""
        branch_id = self.branch.id if at_own_branch else uuid4()
        return Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=branch_id)

    def draft_command(
        self,
        period: BookingPeriod = FIRST_HIRE,
        *,
        quantity: int = DEFAULT_QUANTITY,
        actor: Actor | None = None,
        customer_profile_id: UUID | None = None,
    ) -> CreateReservationCommand:
        """Return the command that asks for a draft of this world's product model.

        Args:
            period: The hire period to book.
            quantity: How many units.
            actor: Who is making the request. The customer themselves when omitted.
            customer_profile_id: The profile staff are booking for.

        """
        return CreateReservationCommand(
            actor=actor or self.customer,
            branch_code=self.branch.code,
            start=period.start,
            end=period.end,
            lines=(RequestedLine(model_slug=self.product_model.slug, quantity=quantity),),
            customer_profile_id=customer_profile_id,
        )

    def stored(self, reservation_id: UUID) -> Reservation:
        """Return the committed reservation with this key.

        Raises:
            LookupError: If nothing with this key was committed.

        """
        for reservation in self.store.committed.reservations:
            if reservation.id == reservation_id:
                return reservation
        raise LookupError(f"No committed reservation has the key {reservation_id}.")


def build_memory_world(
    *,
    asset_count: int = SINGLE_ASSET,
    customer_email: str | None = CUSTOMER_EMAIL,
    email_verified: bool = True,
    account_status: AccountStatus = AccountStatus.ACTIVE,
    trade_discount_percent: Decimal = NO_DISCOUNT,
    min_hire_days: int = MIN_HIRE_DAYS,
    max_hire_days: int = MAX_HIRE_DAYS,
) -> MemoryWorld:
    """Create a store with a branch, a product model, its units and a customer.

    Args:
        asset_count: How many interchangeable units the branch holds. They are
            tagged in order, so the first one is the one allocation picks.
        customer_email: The address of the customer's account, or None to
            build a customer a confirmation cannot be sent to.
        email_verified: Whether the customer has proved that address.
        account_status: The standing of the customer.
        trade_discount_percent: The trade discount on the customer's profile.
        min_hire_days: The shortest hire the model may be booked for.
        max_hire_days: The longest hire the model may be booked for.

    """
    branch = Branch(id=uuid4(), code="CBD", name="Cape Town CBD")
    product_model = ProductModel(
        id=uuid4(),
        sku="TSH-PM-0001",
        name="GBH 2-26 DRE Rotary Hammer",
        slug=MODEL_SLUG,
        daily_rate=DAILY_RATE,
        weekly_rate=WEEKLY_RATE,
        deposit_amount=DEPOSIT,
        late_fee_per_day=LATE_FEE,
        replacement_value=REPLACEMENT_VALUE,
        min_hire_days=min_hire_days,
        max_hire_days=max_hire_days,
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
        account_status=account_status,
        email=customer_email,
        trade_discount_percent=trade_discount_percent,
        email_verified=email_verified,
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


@dataclass(frozen=True, slots=True)
class BookingDesk:
    """Every use case of the booking module, wired over one store.

    Attributes:
        world: The world the use cases work in.
        clock: The clock they share, which a test moves.
        gateway: The email gateway the dispatcher sends through.
        create: Creates a draft.
        hold: Puts a draft on hold.
        confirm: Confirms a hold.
        cancel: Cancels a reservation.
        reads: Reads one reservation or a page of them.
        sweep: Lapses the holds that have run out.

    """

    world: MemoryWorld
    clock: FixedClock
    gateway: NotificationGateway
    create: CreateReservationUseCase
    hold: HoldReservationUseCase
    confirm: ConfirmReservationUseCase
    cancel: CancelReservationUseCase
    reads: ReadReservations
    sweep: ExpireHoldsAndNoShowsUseCase

    def drafted(self, command: CreateReservationCommand | None = None) -> ReservationView:
        """Create a draft, for the world's customer unless a command says otherwise."""
        return self.create.execute(command or self.world.draft_command())

    def held(self, command: CreateReservationCommand | None = None) -> ReservationView:
        """Create a draft, put it on hold as the world's customer and return it."""
        return self.hold.execute(self.command_for(self.drafted(command)))

    def confirmed(self, command: CreateReservationCommand | None = None) -> ReservationView:
        """Create a draft, hold it, confirm it as the world's customer and return it."""
        return self.confirm.execute(self.command_for(self.held(command)))

    def command_for(self, view: ReservationView, actor: Actor | None = None) -> ReservationCommand:
        """Return the command that names a reservation, for the customer unless told otherwise."""
        return ReservationCommand(
            actor=actor or self.world.customer, key=ReservationKey.of(view.detail.id)
        )

    def cancellation_of(
        self, view: ReservationView, *, actor: Actor | None = None, reason: str | None = None
    ) -> CancelReservationCommand:
        """Return the command that cancels a reservation."""
        return CancelReservationCommand(
            actor=actor or self.world.customer, key=ReservationKey.of(view.detail.id), reason=reason
        )


def open_desk(
    world: MemoryWorld,
    *,
    gateway: NotificationGateway | None = None,
    clock: FixedClock | None = None,
    pricing: PricingPolicy | None = None,
) -> BookingDesk:
    """Return every booking use case wired to a world, a gateway and a clock.

    Each use case and the dispatcher are given a unit of work each over the
    same store, which is how the request wiring behaves once one transaction
    has ended and the next begins.

    Args:
        world: The world whose store the use cases commit into.
        gateway: The email gateway. A fake that accepts everything when omitted.
        clock: The clock. A fixed clock at its default instant when omitted.
        pricing: The pricing policy. The standard one when omitted.

    """
    chosen_clock = clock if clock is not None else FixedClock()
    chosen_gateway = gateway if gateway is not None else FakeEmailGateway()
    store = world.store

    def unit_of_work() -> InMemoryUnitOfWork:
        """Return a fresh unit of work over the world's store."""
        return InMemoryUnitOfWork(store)

    sweep = ExpireHoldsAndNoShowsUseCase(unit_of_work(), chosen_clock)
    dispatcher = NotificationDispatcher(unit_of_work(), chosen_gateway, chosen_clock)
    return BookingDesk(
        world=world,
        clock=chosen_clock,
        gateway=chosen_gateway,
        create=CreateReservationUseCase(
            unit_of_work(), chosen_clock, pricing or StandardPricingPolicy()
        ),
        hold=HoldReservationUseCase(unit_of_work(), chosen_clock, sweep),
        confirm=ConfirmReservationUseCase(unit_of_work(), chosen_clock, sweep, dispatcher),
        cancel=CancelReservationUseCase(unit_of_work(), chosen_clock),
        reads=ReadReservations(unit_of_work(), chosen_clock, sweep),
        sweep=sweep,
    )


__all__ = [
    "CUSTOMER_EMAIL",
    "FIRST_HIRE",
    "MODEL_SLUG",
    "BookingDesk",
    "MemoryWorld",
    "build_memory_world",
    "open_desk",
]
