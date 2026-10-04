"""Gross contribution, which is the second of the report's two definitions.

Gross contribution, per asset, for a period, is the hire revenue excluding VAT
attributed to that asset, plus the late fees and the damage recovery charged on
it excluding VAT, less the actual repair costs recorded against it. It leaves
out acquisition cost, depreciation, finance, staff and premises costs and every
overhead, because the system holds none of them. So it is called gross
contribution everywhere and never profit.

`Contribution` holds the four parts and works the figure out, and it is the one
place that does. The parts of a group of units are the sums of the parts of
its units, and the figure of the group is worked out from those sums, so the
rows and the totals of the report always agree to the cent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.money import Money


@dataclass(frozen=True, slots=True)
class Contribution:
    """The four parts of gross contribution, for one unit or a group of them.

    Attributes:
        hire_revenue: Hire charges attributed to the unit, excluding VAT.
        late_fees: Late fees charged on it, excluding VAT.
        damage_recovery: Damage recovery charged on it, and the deposit kept
            for it when it was lost, excluding VAT.
        repair_costs: The actual repair costs of the reports resolved against it.

    """

    hire_revenue: Money
    late_fees: Money
    damage_recovery: Money
    repair_costs: Money

    @classmethod
    def nothing(cls) -> Contribution:
        """Return a contribution with every part at nought."""
        return cls(Money.zero(), Money.zero(), Money.zero(), Money.zero())

    @property
    def gross_contribution(self) -> Money:
        """Return revenue, late fees and recovery, less repair costs, to the cent."""
        earned = self.hire_revenue.add(self.late_fees).add(self.damage_recovery)
        return earned.subtract(self.repair_costs).rounded()

    def plus(self, other: Contribution) -> Contribution:
        """Return the parts of this contribution and another added together."""
        return Contribution(
            hire_revenue=self.hire_revenue.add(other.hire_revenue),
            late_fees=self.late_fees.add(other.late_fees),
            damage_recovery=self.damage_recovery.add(other.damage_recovery),
            repair_costs=self.repair_costs.add(other.repair_costs),
        )
