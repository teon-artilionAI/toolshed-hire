"""Object factories.

Every table in the schema carries columns that are not null and constraints
that are not obvious, for example that a counter assistant must carry a branch
and that nothing else may. A test that has to satisfy all of that by hand stops
being about the behaviour it is named after, so the required shape lives here
once and a test overrides only the field it actually cares about.

Only the tables the existing flows write to have a factory. The rest gain one
when the flow that needs it is built.

The factories flush but never commit. The transaction boundary belongs to the
test, which is the same rule the application follows.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final

from sqlmodel import Session

from app.domain.enums import (
    AccountStatus,
    AssetStatus,
    ConditionGrade,
    CustomerType,
    IdDocType,
    ReleaseReason,
    ReservationStatus,
    UserRole,
)
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Category,
    CustomerProfile,
    ProductModel,
    Reservation,
    ReservationLine,
    UserAccount,
)
from app.infrastructure.security import hash_password

logger = logging.getLogger(__name__)

TEST_PASSWORD: Final[str] = "correct-horse-battery-staple"
DEFAULT_QUANTITY: Final[int] = 1
FIRST_LINE_POSITION: Final[int] = 1
DEFAULT_DAILY_RATE: Final[Decimal] = Decimal("185.00")
DEFAULT_WEEKLY_RATE: Final[Decimal] = Decimal("740.00")
DEFAULT_DEPOSIT: Final[Decimal] = Decimal("600.00")
DEFAULT_LATE_FEE: Final[Decimal] = Decimal("120.00")
DEFAULT_REPLACEMENT_VALUE: Final[Decimal] = Decimal("4200.00")
DEFAULT_ACQUISITION_COST: Final[Decimal] = Decimal("3980.00")
ACQUIRED_ON: Final[date] = date(2024, 6, 11)
OPENS_AT: Final[time] = time(7, 0)
CLOSES_AT: Final[time] = time(17, 0)
# The factories price nothing. A test that cares about a total sets it.
NO_CHARGE: Final[Decimal] = Decimal("0.00")

_counter: Final[itertools.count[int]] = itertools.count(1)
_password_hash_cache: dict[str, str] = {}


def _next_index() -> int:
    """Return a process unique integer, used to keep natural keys distinct."""
    return next(_counter)


def cached_password_hash(plain_password: str = TEST_PASSWORD) -> str:
    """Return the bcrypt hash of a test password, computing it at most once.

    bcrypt at work factor 12 costs roughly a quarter of a second per call. That
    is the point of the work factor in production and pure waste in a test
    suite that creates the same password fifty times, so the result is cached
    per distinct password rather than the work factor being lowered.

    Args:
        plain_password: The password to hash.

    Returns:
        The bcrypt hash, identical to what the application would store.

    """
    if plain_password not in _password_hash_cache:
        logger.debug("test.password_hash_computed", extra={"cache_size": len(_password_hash_cache)})
        _password_hash_cache[plain_password] = hash_password(plain_password)
    return _password_hash_cache[plain_password]


@dataclass(frozen=True, slots=True)
class Factory:
    """Builds valid rows in one session. Flushes so ids exist, never commits."""

    session: Session

    def branch(self, *, code: str | None = None, name: str = "Cape Town CBD") -> Branch:
        """Create a trading branch.

        Args:
            code: The branch code. Generated when omitted so two branches in one
                test cannot collide on the unique code.
            name: The display name.

        """
        branch = Branch(
            code=code or f"B{_next_index():03d}",
            name=name,
            street_address="14 Albert Road",
            suburb="Woodstock",
            city="Cape Town",
            postal_code="7925",
            phone="021 555 0101",
            opens_at=OPENS_AT,
            closes_at=CLOSES_AT,
            is_active=True,
        )
        self.session.add(branch)
        self.session.flush()
        return branch

    def category(self, *, name: str = "Drilling and Demolition") -> Category:
        """Create a top level catalogue category."""
        index = _next_index()
        category = Category(code=f"CAT-{index:04d}", name=name, slug=f"category-{index}")
        self.session.add(category)
        self.session.flush()
        return category

    def product_model(
        self, *, name: str = "GBH 2-26 DRE Rotary Hammer", category: Category | None = None
    ) -> ProductModel:
        """Create a catalogue entry with money held as NUMERIC, never float.

        Args:
            name: The display name.
            category: The category that classifies the model. One is created
                when omitted, because a model cannot exist without one.

        """
        index = _next_index()
        model = ProductModel(
            sku=f"TSH-PM-{index:04d}",
            name=name,
            slug=f"product-model-{index}",
            category_id=(category or self.category()).id,
            manufacturer="Bosch",
            model_number="GBH 2-26 DRE",
            short_description="SDS-plus rotary hammer, 800 W, 2.7 J impact energy.",
            daily_rate=DEFAULT_DAILY_RATE,
            weekly_rate=DEFAULT_WEEKLY_RATE,
            deposit_amount=DEFAULT_DEPOSIT,
            late_fee_per_day=DEFAULT_LATE_FEE,
            replacement_value=DEFAULT_REPLACEMENT_VALUE,
            is_published=True,
        )
        self.session.add(model)
        self.session.flush()
        return model

    def asset(
        self,
        *,
        product_model: ProductModel,
        branch: Branch,
        asset_tag: str | None = None,
        status: AssetStatus = AssetStatus.AVAILABLE,
    ) -> Asset:
        """Create one physical unit of a product model at a branch."""
        asset = Asset(
            asset_tag=asset_tag or f"TSH-TS-{_next_index():04d}",
            product_model_id=product_model.id,
            branch_id=branch.id,
            status=status,
            condition_grade=ConditionGrade.A,
            acquired_on=ACQUIRED_ON,
            acquisition_cost=DEFAULT_ACQUISITION_COST,
        )
        self.session.add(asset)
        self.session.flush()
        return asset

    def user(
        self,
        *,
        role: UserRole = UserRole.CUSTOMER,
        email: str | None = None,
        branch: Branch | None = None,
        is_active: bool = True,
        password: str = TEST_PASSWORD,
    ) -> UserAccount:
        """Create an account.

        Raises:
            ValueError: If the branch scope contradicts the role. Counter staff
                are branch scoped and nobody else is, which the database
                enforces with `ck_user_account_branch_scope`. Failing here
                gives the reader the reason rather than a check constraint
                violation five lines later.

        """
        needs_branch = role is UserRole.COUNTER_STAFF
        if needs_branch and branch is None:
            raise ValueError(
                "Attempted to build a COUNTER_STAFF account with no branch. Every counter "
                "assistant is branch scoped (ck_user_account_branch_scope)."
            )
        if not needs_branch and branch is not None:
            raise ValueError(
                f"Attempted to build a {role.value} account carrying a branch. Only "
                "COUNTER_STAFF is branch scoped (ck_user_account_branch_scope)."
            )
        account = UserAccount(
            email=email or f"person{_next_index()}@toolshedhire.co.za",
            password_hash=cached_password_hash(password),
            role=role,
            full_name="Wesley Adonis",
            branch_id=branch.id if branch else None,
            is_active=is_active,
        )
        self.session.add(account)
        self.session.flush()
        return account

    def customer_profile(
        self, *, branch: Branch, account: UserAccount | None = None
    ) -> CustomerProfile:
        """Create the hire profile of a customer.

        Args:
            branch: The branch that registered the customer.
            account: The sign in account the profile belongs to. Omit it to
                build a walk-in, which has a profile and no login.

        """
        profile = CustomerProfile(
            user_account_id=account.id if account else None,
            customer_type=CustomerType.INDIVIDUAL,
            display_name=account.full_name if account else "Nomsa Dlamini",
            id_document_type=IdDocType.SA_ID,
            id_document_last4="4189",
            contact_phone="082 441 7719",
            billing_address_line1="27 Durham Avenue",
            billing_suburb="Salt River",
            billing_city="Cape Town",
            billing_postal_code="7925",
            account_status=AccountStatus.ACTIVE,
            registered_branch_id=branch.id,
        )
        self.session.add(profile)
        self.session.flush()
        return profile

    def reservation(
        self,
        *,
        profile: CustomerProfile,
        created_by: UserAccount,
        branch: Branch,
        period: BookingPeriod,
    ) -> Reservation:
        """Create a held reservation covering the given period.

        Args:
            profile: The customer the booking belongs to.
            created_by: The account that raised it, the customer or an assistant.
            branch: The collection branch.
            period: The half open hire period.

        """
        reservation = Reservation(
            reference=f"TSH-R-26-{_next_index():06d}",
            customer_profile_id=profile.id,
            branch_id=branch.id,
            status=ReservationStatus.HELD,
            start_date=period.start,
            end_date=period.end,
            subtotal_ex_vat=NO_CHARGE,
            vat_amount=NO_CHARGE,
            deposit_total=NO_CHARGE,
            estimated_total_inc_vat=NO_CHARGE,
            created_by_user_id=created_by.id,
        )
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def reservation_line(
        self,
        *,
        reservation: Reservation,
        product_model: ProductModel,
        quantity: int = DEFAULT_QUANTITY,
    ) -> ReservationLine:
        """Create the single line the skeleton reservations carry."""
        line = ReservationLine(
            reservation_id=reservation.id,
            product_model_id=product_model.id,
            quantity=quantity,
            line_position=FIRST_LINE_POSITION,
            daily_rate_snapshot=DEFAULT_DAILY_RATE,
            weekly_rate_snapshot=DEFAULT_WEEKLY_RATE,
            deposit_snapshot=DEFAULT_DEPOSIT,
            late_fee_per_day_snapshot=DEFAULT_LATE_FEE,
            replacement_value_snapshot=DEFAULT_REPLACEMENT_VALUE,
            line_subtotal_ex_vat=NO_CHARGE,
        )
        self.session.add(line)
        self.session.flush()
        return line

    def allocation(
        self,
        *,
        line: ReservationLine,
        asset: Asset,
        period: BookingPeriod,
        released_at: datetime | None = None,
        release_reason: ReleaseReason | None = None,
    ) -> AssetAllocation:
        """Build an allocation row without flushing it.

        Deliberately not flushed. Half the tests that use this expect the flush
        to fail, and they need to own the moment it happens so they can catch
        the IntegrityError around exactly one statement.

        Args:
            line: The reservation line the allocation belongs to.
            asset: The physical unit being held.
            period: The half open period being held.
            released_at: When the allocation stopped occupying the asset. Left
                as None, the allocation is active.
            release_reason: Why it was released. It must be set exactly when
                `released_at` is, which is what
                `ck_asset_allocation_release_state` enforces.

        """
        return AssetAllocation(
            reservation_line_id=line.id,
            asset_id=asset.id,
            branch_id=asset.branch_id,
            start_date=period.start,
            end_date=period.end,
            allocated_at=datetime.now(UTC),
            released_at=released_at,
            release_reason=release_reason,
        )


__all__ = ["TEST_PASSWORD", "Factory", "cached_password_hash"]
