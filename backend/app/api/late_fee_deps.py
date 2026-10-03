"""The dependency of the late fee policy, the second Strategy (BR-30, BR-31).

This module chooses the late fee policy, and it is the only place that knows
`StandardLateFeePolicy` stands behind the `LateFeePolicy` port, the way
`app/api/pricing_deps.py` chooses the pricing policy. The hire dependencies
hand it to returns, losses and the reads of a rental, and the counter's
dependencies hand it to the dashboard, so every late fee the API shows or
charges comes from the one policy.

It is in a module of its own because the hire and the counter dependencies
both need it, and neither may import the other.

The policy is built once, when the application starts, and every request is
handed the same one. It holds no state, so sharing it is safe. A test
overrides `get_late_fee_policy` to charge with a policy of its own.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Depends

from app.domain.policies.late_fee import LateFeePolicy
from app.domain.policies.standard_late_fee import StandardLateFeePolicy

_STANDARD_LATE_FEE_POLICY: Final[LateFeePolicy] = StandardLateFeePolicy()


def get_late_fee_policy() -> LateFeePolicy:
    """Return the late fee policy the running application charges with."""
    return _STANDARD_LATE_FEE_POLICY


LateFeePolicyDependency = Annotated[LateFeePolicy, Depends(get_late_fee_policy)]
