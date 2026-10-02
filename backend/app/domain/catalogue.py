"""The catalogue and fleet entities, which are the product model and the physical asset.

This is the split the whole design rests on. A product model is what a customer
shops for. An asset is the individually tagged unit that is allocated, collected
and returned. Availability is the allocation of specific assets and never a
quantity counter.

Money is held as `Decimal` here, as the database hands it over. A price is
worked out with the `Money` value object in `app.domain.money`, and the pricing
policy is handed a snapshot of these figures and never the entry itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import DetailValue, ValidationFailure
from app.domain.period import PERIOD_BOUNDS_RULE, BookingPeriod

SINGLE_DAY: Final[int] = 1


@dataclass(frozen=True, slots=True)
class ProductModel:
    """A catalogue entry, with the prices a reservation line snapshots (BR-20).

    Attributes:
        id: The product model key.
        sku: The stock keeping unit, used in logs and on paperwork.
        name: The display name.
        slug: The name the model carries in an address.
        daily_rate: The rate for one day, excluding VAT.
        weekly_rate: The rate for each complete seven days, excluding VAT.
        deposit_amount: The deposit held for one unit.
        late_fee_per_day: The fee for each day a unit comes back late.
        replacement_value: The cap on damage recovery for one unit (BR-39).
        min_hire_days: The shortest hire the model may be booked for.
        max_hire_days: The longest hire the model may be booked for (BR-03).

    """

    id: UUID
    sku: str
    name: str
    slug: str
    daily_rate: Decimal
    weekly_rate: Decimal
    deposit_amount: Decimal
    late_fee_per_day: Decimal
    replacement_value: Decimal
    min_hire_days: int
    max_hire_days: int

    def ensure_can_be_hired_for(self, period: BookingPeriod) -> None:
        """Refuse a period shorter or longer than this model may be hired for.

        The sentence names the model, because a reservation can carry several
        and the customer has to know which one the dates do not suit.

        Raises:
            ValidationFailure: If the period is outside the hire limits of the
                model. The rule and the figures travel beside the sentence,
                for the log.

        """
        detail: dict[str, DetailValue] = {
            "sku": self.sku,
            "hire_days": period.days,
            "min_hire_days": self.min_hire_days,
            "max_hire_days": self.max_hire_days,
        }
        if period.days > self.max_hire_days:
            raise ValidationFailure(
                f"{self.name} can be hired for at most {_days_in_words(self.max_hire_days)}.",
                detail,
                rule=PERIOD_BOUNDS_RULE,
            )
        if period.days < self.min_hire_days:
            raise ValidationFailure(
                f"{self.name} has to be hired for at least "
                f"{_days_in_words(self.min_hire_days)}.",
                detail,
                rule=PERIOD_BOUNDS_RULE,
            )


def _days_in_words(days: int) -> str:
    """Return a number of days as a customer reads it, "1 day" or "5 days"."""
    return f"{days} day" if days == SINGLE_DAY else f"{days} days"


@dataclass(frozen=True, slots=True)
class Asset:
    """One individually tagged physical unit, for example TSH-DR-0042.

    Attributes:
        id: The asset key.
        asset_tag: The tag painted on the machine, immutable once assigned.
        product_model_id: The catalogue entry this unit realises.
        branch_id: The branch that holds the unit.
        status: Where the unit is in its lifecycle.
        condition_grade: The grade recorded at the last checkout or return.

    """

    id: UUID
    asset_tag: str
    product_model_id: UUID
    branch_id: UUID
    status: AssetStatus
    condition_grade: ConditionGrade

    def is_allocatable(self) -> bool:
        """Return True when the unit may be held for a future hire.

        Only an `AVAILABLE` unit qualifies. Whether it is free for a particular
        period is a separate question, answered by its allocations and finally
        by the exclusion constraint.
        """
        return self.status is AssetStatus.AVAILABLE
