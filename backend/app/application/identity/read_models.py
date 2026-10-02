"""What the branch directory hands back.

A visitor chooses a branch before anything else, so the directory is read with
no account. It carries what a person needs to find the branch and ring it, and
nothing about its stock or its staff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class BranchListing:
    """One trading branch, as a visitor sees it.

    Attributes:
        code: The short code, for example CBD. It is what a search is filtered by.
        name: The display name.
        suburb: The suburb the branch trades from.
        city: The city.
        phone: The number of the counter.
        opens_at: When the counter opens, in local time.
        closes_at: When the counter closes, in local time.

    """

    code: str
    name: str
    suburb: str
    city: str
    phone: str
    opens_at: time
    closes_at: time
