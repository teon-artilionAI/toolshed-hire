"""The three Toolshed Hire branches.

I keep the suburbs the prototype already shows. The street addresses and the
phone numbers are made up, so nobody real gets a call from a demonstration.
"""

from datetime import time

from .types import BranchSeed

OPENS_AT = time(7, 0)
CLOSES_AT = time(17, 0)
CITY = "Cape Town"

BRANCHES: tuple[BranchSeed, ...] = (
    BranchSeed(
        code="CBD",
        name="Cape Town CBD",
        street_address="118 Albert Road",
        suburb="Woodstock",
        city=CITY,
        postal_code="7925",
        phone="021 555 0142",
        opens_at=OPENS_AT,
        closes_at=CLOSES_AT,
    ),
    BranchSeed(
        code="BLV",
        name="Bellville",
        street_address="27 La Belle Road",
        suburb="Stikland",
        city=CITY,
        postal_code="7530",
        phone="021 555 0157",
        opens_at=OPENS_AT,
        closes_at=CLOSES_AT,
    ),
    BranchSeed(
        code="SMW",
        name="Somerset West",
        street_address="9 Main Road",
        suburb="Firgrove",
        city=CITY,
        postal_code="7110",
        phone="021 555 0163",
        opens_at=OPENS_AT,
        closes_at=CLOSES_AT,
    ),
)
