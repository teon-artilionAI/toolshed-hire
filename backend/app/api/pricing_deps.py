"""The dependencies of pricing, which is the policy and the quote.

This is the pricing half of the composition root. `app/api/deps.py` wires the
use cases that write and `app/api/catalogue_deps.py` wires the reads. This
module chooses the pricing policy, and it is the only place that knows
`StandardPricingPolicy` stands behind the `PricingPolicy` port.

The policy is built once, when the application starts, and every request is
handed the same one. It holds no state, so sharing it is safe. A test overrides
`get_pricing_policy` to price with a policy of its own.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Depends

from app.api.catalogue_deps import CatalogueQueryDependency
from app.api.deps import ClockDependency
from app.application.money.quote import QuoteHire
from app.domain.policies.pricing import PricingPolicy
from app.domain.policies.standard_pricing import StandardPricingPolicy

_STANDARD_PRICING_POLICY: Final[PricingPolicy] = StandardPricingPolicy()


def get_pricing_policy() -> PricingPolicy:
    """Return the pricing policy the running application prices with."""
    return _STANDARD_PRICING_POLICY


PricingPolicyDependency = Annotated[PricingPolicy, Depends(get_pricing_policy)]


def get_quote_hire(
    catalogue: CatalogueQueryDependency,
    pricing: PricingPolicyDependency,
    clock: ClockDependency,
) -> QuoteHire:
    """Return the quote service, wired to its query object, its policy and its clock."""
    return QuoteHire(catalogue, pricing, clock)


QuoteHireDependency = Annotated[QuoteHire, Depends(get_quote_hire)]
