"""Object factories.

Every table in the skeleton carries columns that are not null and constraints
that are not obvious, for example that a counter assistant must carry a branch
and that nothing else may. A test that has to satisfy all of that by hand stops
being about the behaviour it is named after, so the required shape lives here
once and a test overrides only the field it actually cares about.

The factories flush but never commit. The transaction boundary belongs to the
test, which is the same rule the application follows.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final

from sqlmodel import Session

from app.domain.enums import (
    AllocationStatus,
    AssetStatus,
    ConditionGrade,
    ReservationStatus,
    UserRole,
)
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
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
DEFAULT_DEPOSIT: Final[Decimal] = Decimal("600.00")
DEFAULT_LATE_FEE: Final[Decimal] = Decimal("120.00")
DEFAULT_REPLACEMENT_VALUE: Final[Decimal] = Decimal("4200.00")
DEFAULT_ACQUISITION_COST: Final[Decimal] = Decimal("3980.00")
ACQUIRED_ON: Final[date] = date(2024, 6, 11)

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
            suburb="Woodstock",
            city="Cape Town",
            is_active=True,
        )
        self.session.add(branch)
        self.session.flush()
        return branch

    def product_model(self, *, name: str = "GBH 2-26 DRE Rotary Hammer") -> ProductModel:
        """Create a catalogue entry with money held as NUMERIC, never float."""
        index = _next_index()
        model = ProductModel(
            sku=f"TSH-PM-{index:04d}",
            name=name,
            slug=f"product-model-{index}",
            manufacturer="Bosch",
            short_description="SDS-plus rotary hammer, 800 W, 2.7 J impact energy.",
            daily_rate=DEFAULT_DAILY_RATE,
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
                enforces with `ck_user_accounts_branch_scope`. Failing here
                gives the reader the reason rather than a check constraint
                violation five lines later.

        """
        needs_branch = role is UserRole.COUNTER_STAFF
        if needs_branch and branch is None:
            raise ValueError(
                "Attempted to build a COUNTER_STAFF account with no branch. Every counter "
                "assistant is branch scoped (ck_user_accounts_branch_scope)."
            )
        if not needs_branch and branch is not None:
            raise ValueError(
                f"Attempted to build a {role.value} account carrying a branch. Only "
                "COUNTER_STAFF is branch scoped (ck_user_accounts_branch_scope)."
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

    def reservation(
        self, *, customer: UserAccount, branch: Branch, period: BookingPeriod
    ) -> Reservation:
        """Create a held reservation covering the given period."""
        reservation = Reservation(
            reference=f"TSH-R-26-{_next_index():06d}",
            customer_user_id=customer.id,
            branch_id=branch.id,
            status=ReservationStatus.HELD,
            start_date=period.start,
            end_date=period.end,
            created_by_user_id=customer.id,
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
            deposit_snapshot=DEFAULT_DEPOSIT,
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
        status: AllocationStatus = AllocationStatus.ACTIVE,
        released_at: datetime | None = None,
    ) -> AssetAllocation:
        """Build an allocation row without flushing it.

        Deliberately not flushed. Half the tests that use this expect the flush
        to fail, and they need to own the moment it happens so they can catch
        the IntegrityError around exactly one statement.

        Args:
            line: The reservation line the allocation belongs to.
            asset: The physical unit being held.
            period: The half open period being held.
            status: ACTIVE unless the test is building released history.
            released_at: Must be set for any status other than ACTIVE, which is
                what `ck_asset_allocations_release_state` enforces.

        """
        return AssetAllocation(
            reservation_line_id=line.id,
            asset_id=asset.id,
            branch_id=asset.branch_id,
            start_date=period.start,
            end_date=period.end,
            status=status,
            allocated_at=datetime.now(UTC),
            released_at=released_at,
        )


__all__ = ["TEST_PASSWORD", "Factory", "cached_password_hash"]
