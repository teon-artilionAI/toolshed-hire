"""The policies of the domain, which are the rules that can be swapped.

A policy is a port with one implementation that runs in production and a
counterpart for tests. The pricing policy is the first. The late fee policy
joins it when returns are built.
"""

from __future__ import annotations

from app.domain.policies.fixed_rate_pricing import FixedRatePricingPolicy
from app.domain.policies.pricing import (
    HireQuote,
    InvalidPricingInput,
    LineSnapshot,
    PricingBasis,
    PricingPolicy,
)
from app.domain.policies.standard_pricing import StandardPricingPolicy
from app.domain.policies.totals import HireTotals, totals_of

__all__ = [
    "FixedRatePricingPolicy",
    "HireQuote",
    "HireTotals",
    "InvalidPricingInput",
    "LineSnapshot",
    "PricingBasis",
    "PricingPolicy",
    "StandardPricingPolicy",
    "totals_of",
]
