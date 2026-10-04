"""What goes wrong with a unit that comes back damaged, and what putting it right costs.

Nothing here touches a database. About one hire in forty brings a unit back
damaged. The counter flags it, files a report that same visit, and the unit
goes to the workshop and comes back on the shelf once the report is resolved
with what the repair actually cost.

A repair is priced from the replacement value of the model, a small share of
it for minor damage and a larger one for major damage, kept between a floor
and a ceiling so a cheap grinder is not repaired for a few rand and a roller
is not repaired for the price of a car. Half the time the customer is charged
for it. The recovery is the estimate with VAT added, rounded to ten rand, and
it always stays under the replacement value, which is the cap the domain
enforces (BR-39).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from random import Random
from types import MappingProxyType
from typing import Final

from app.domain.enums import DamageSeverity
from app.domain.money import Money
from app.domain.vat import VAT_RATE_PERCENT
from seeding.trading_demand import CHARGEABLE_DAMAGE_CHANCE

MAJOR_DAMAGE_CHANCE: Final[float] = 0.2
PER_MILLE: Final[int] = 1000
PERCENT: Final[int] = 100
# The share of the replacement value a repair is estimated at, in tenths of a percent.
MINOR_SHARE_PER_MILLE: Final[tuple[int, int]] = (30, 80)
MAJOR_SHARE_PER_MILLE: Final[tuple[int, int]] = (80, 160)
SMALLEST_ESTIMATE: Final[Money] = Money(Decimal("250.00"))
LARGEST_ESTIMATE: Final[Money] = Money(Decimal("18000.00"))
# What the repair came to against its estimate, in percent.
ACTUAL_COST_PERCENT: Final[tuple[int, int]] = (85, 120)
# The most a recovery may be, as a share of the replacement value in percent.
RECOVERY_CEILING_PERCENT: Final[int] = 90
TEN_RAND: Final[Decimal] = Decimal("10")
WHOLE: Final[Decimal] = Decimal("1")
# Days in the workshop before the report is resolved.
MINOR_REPAIR_DAYS: Final[tuple[int, int]] = (2, 5)
MAJOR_REPAIR_DAYS: Final[tuple[int, int]] = (5, 11)

MINOR_RESOLUTION: Final[str] = "Repaired in the workshop and tested before going back on the shelf."
MAJOR_RESOLUTION: Final[str] = (
    "Parts replaced by the agent, serviced and tested before going back on the shelf."
)
ANY_CATEGORY_DAMAGE: Final[tuple[str, ...]] = ("Casing cracked and a guard missing.",)
# What the counter writes on a report, by the category the model sits in.
DAMAGE_BY_CATEGORY: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "BREAK-DRILL": (
            "Chuck seized and will not release a bit.",
            "Gearbox housing cracked after a fall from a scaffold.",
        ),
        "COMPACTION": (
            "Base plate bent after use on rubble.",
            "Pull starter cord snapped and the recoil spring broken.",
        ),
        "CONCRETE-MIX": (
            "Drum ring gear chipped and jumping teeth.",
            "Vibrator hose split near the coupling.",
        ),
        "CUT-GRIND": (
            "Blade guard bent and rubbing on the disc.",
            "Power cable cut through near the plug.",
        ),
        "FLOOR-PREP": (
            "Drum bearing collapsed and the drum out of true.",
            "Dust bag torn and the fan housing cracked.",
        ),
        "ACCESS": (
            "Brace bent and the locking clip sheared off.",
            "Castor wheel broken off a leg.",
        ),
        "LIFTING": (
            "Hydraulic ram leaking at the seal.",
            "Chain stretched past its wear limit.",
        ),
        "GARDEN": (
            "Gearbox head cracked after striking a rock.",
            "Chain and guide bar damaged by a nail.",
        ),
        "POWER-LIGHT": (
            "Output socket burnt and the breaker will not reset.",
            "Fuel tank dented and leaking at the seam.",
        ),
        "PUMPS": (
            "Impeller chipped by stones in the intake.",
            "Suction hose split and the strainer missing.",
        ),
        "WELDING": (
            "Torch lead cut and the earth clamp broken.",
            "Wire feed rollers worn through by the wrong wire size.",
        ),
        "CLEANING": (
            "High pressure hose burst and the lance bent.",
            "Brush deck cracked against a kerb.",
        ),
        "SITE-EQUIP": (
            "Burner nozzle blocked and the ignition lead burnt.",
            "Tripod leg bent and the laser out of calibration.",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class DamagePlan:
    """What went wrong with one unit and what it cost to put right.

    Attributes:
        severity: How bad the counter judged it.
        description: What the counter wrote on the report.
        repair_estimate: What the repair was expected to cost.
        actual_repair_cost: What it cost, which the report is resolved with.
        recovery_inc_vat: What the customer is charged including VAT, or None
            when the damage is not charged to them.
        repair_days: The days from the return to the report being resolved.
        resolution_notes: What the report is closed with.

    """

    severity: DamageSeverity
    description: str
    repair_estimate: Money
    actual_repair_cost: Money
    recovery_inc_vat: Money | None
    repair_days: int
    resolution_notes: str


def plan_damage(rng: Random, category_code: str, replacement_value: Money) -> DamagePlan:
    """Draw the damage of one unit of a model, its cost and whether the customer pays.

    Args:
        rng: The seeded generator every choice of the history is drawn from.
        category_code: The category the model sits in, which picks the wording.
        replacement_value: The replacement value of the model, which prices
            the repair and caps the recovery.

    """
    major = rng.random() < MAJOR_DAMAGE_CHANCE
    share = rng.randint(*(MAJOR_SHARE_PER_MILLE if major else MINOR_SHARE_PER_MILLE))
    estimate = _bounded(_to_ten_rand(replacement_value.in_proportion(share, PER_MILLE)))
    actual = estimate.in_proportion(rng.randint(*ACTUAL_COST_PERCENT), PERCENT).rounded()
    chargeable = rng.random() < CHARGEABLE_DAMAGE_CHANCE
    wording = DAMAGE_BY_CATEGORY.get(category_code, ANY_CATEGORY_DAMAGE)
    return DamagePlan(
        severity=DamageSeverity.MAJOR if major else DamageSeverity.MINOR,
        description=rng.choice(wording),
        repair_estimate=estimate,
        actual_repair_cost=actual,
        recovery_inc_vat=_recovery(estimate, replacement_value) if chargeable else None,
        repair_days=rng.randint(*(MAJOR_REPAIR_DAYS if major else MINOR_REPAIR_DAYS)),
        resolution_notes=MAJOR_RESOLUTION if major else MINOR_RESOLUTION,
    )


def _recovery(estimate: Money, replacement_value: Money) -> Money:
    """Return the estimate with VAT added, to ten rand, and never above the ceiling."""
    with_vat = _to_ten_rand(estimate.add(estimate.percent_of(VAT_RATE_PERCENT)))
    ceiling = replacement_value.in_proportion(RECOVERY_CEILING_PERCENT, PERCENT).rounded()
    return min(with_vat, ceiling)


def _bounded(estimate: Money) -> Money:
    """Return an estimate kept between the smallest and the largest a repair is priced at."""
    return max(SMALLEST_ESTIMATE, min(estimate, LARGEST_ESTIMATE))


def _to_ten_rand(amount: Money) -> Money:
    """Return an amount rounded half up to the nearest ten rand, as a workshop quotes."""
    tens = (amount.amount / TEN_RAND).quantize(WHOLE, rounding=ROUND_HALF_UP)
    return Money(tens * TEN_RAND).rounded()
