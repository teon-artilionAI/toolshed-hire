"""The two definitions the report is read by, written once.

The screen shows them, the CSV repeats them in its first line and the README
states them, each in these words. Gross contribution is never called profit,
because the system holds none of the costs that would make it one.
"""

from __future__ import annotations

from typing import Final

UTILISATION_DEFINITION: Final[str] = (
    "Utilisation, per asset, for a period. The days the asset was on an active allocation "
    "within the period, divided by the days it was in the fleet and serviceable within the "
    "period. Days quarantined, under repair, lost or retired are left out of the denominator. "
    "Days are half open, [from, to)."
)
GROSS_CONTRIBUTION_DEFINITION: Final[str] = (
    "Gross contribution, per asset, for a period. Hire revenue excluding VAT attributed to "
    "that asset, plus late fees and damage recovery charged on it (excluding VAT), less the "
    "actual repair costs recorded against it. It excludes acquisition cost, depreciation, "
    "finance, staff and premises costs and all overheads. It is labelled gross contribution "
    "everywhere, never profit."
)
NOT_PROFIT_NOTICE: Final[str] = "These are gross contribution figures and not profit."
