"""The reference a customer quotes for a reservation, for example TSH-R-26-000124.

The number comes from a database sequence, which the reservation repository
draws. This module only says how the year and that number are written.
"""

from __future__ import annotations

from typing import Final

REFERENCE_PREFIX: Final[str] = "TSH-R"
REFERENCE_YEAR_MODULUS: Final[int] = 100


def format_reference(year: int, sequence_value: int) -> str:
    """Return a reservation reference, for example TSH-R-26-000124.

    Args:
        year: The calendar year the hire starts in. Only its last two digits
            are used.
        sequence_value: The next value of the reference sequence.

    """
    return f"{REFERENCE_PREFIX}-{year % REFERENCE_YEAR_MODULUS:02d}-{sequence_value:06d}"
