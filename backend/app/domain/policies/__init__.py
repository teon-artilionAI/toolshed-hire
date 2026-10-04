"""The policies of the domain, which are the rules that can be swapped.

A policy is a port with one implementation that runs in production and a
counterpart for tests. There are two, the two Strategies the design document
names. The pricing policy works out what a hire costs (BR-21), and the late
fee policy works out what a unit owes for coming back late (BR-30, BR-31).

Beside them sits one rule that is not swapped, the share of a hire charge each
unit of a hire is given in the utilisation report, in `hire_charge_share`. It
is here because it scales an amount, and every place that does is kept in this
package and in the VAT module.
"""

from __future__ import annotations

from app.domain.policies.fixed_late_fee import FixedLateFeePolicy
from app.domain.policies.fixed_rate_pricing import FixedRatePricingPolicy
from app.domain.policies.late_fee import InvalidLateFeeInput, LateFee, LateFeePolicy
from app.domain.policies.pricing import (
    HireQuote,
    InvalidPricingInput,
    LineSnapshot,
    PricingBasis,
    PricingPolicy,
)
from app.domain.policies.standard_late_fee import StandardLateFeePolicy
from app.domain.policies.standard_pricing import StandardPricingPolicy
from app.domain.policies.totals import HireTotals, totals_of

__all__ = [
    "FixedLateFeePolicy",
    "FixedRatePricingPolicy",
    "HireQuote",
    "HireTotals",
    "InvalidLateFeeInput",
    "InvalidPricingInput",
    "LateFee",
    "LateFeePolicy",
    "LineSnapshot",
    "PricingBasis",
    "PricingPolicy",
    "StandardLateFeePolicy",
    "StandardPricingPolicy",
    "totals_of",
]
