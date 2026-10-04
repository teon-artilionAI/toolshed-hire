"""What one seed run created and what it found already in place."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("seed")


@dataclass(slots=True)
class SeedTally:
    """Counts, per kind of row, what a run created and what it left alone.

    A kind is a short label such as `branch` or `asset`. I keep the two counts
    apart because the difference is the whole answer to whether a second run
    changed anything.
    """

    created: dict[str, int] = field(default_factory=dict)
    found: dict[str, int] = field(default_factory=dict)
    corrected: dict[str, int] = field(default_factory=dict)

    def record(self, kind: str, *, created: int, found: int) -> None:
        """Add the outcome of loading one kind of row and log it.

        Args:
            kind: The label the counts are kept under.
            created: How many rows this run inserted.
            found: How many rows were already there and were left unchanged.

        Raises:
            ValueError: If either count is negative, which can only be a bug in
                the loader that called this.

        """
        if created < 0 or found < 0:
            raise ValueError(
                f"Attempted to record {created} created and {found} found rows of kind "
                f"{kind!r}. A count cannot be negative."
            )
        self.created[kind] = self.created.get(kind, 0) + created
        self.found[kind] = self.found.get(kind, 0) + found
        logger.info(
            "seed.rows_loaded",
            extra={"kind": kind, "created_count": created, "found_count": found},
        )

    def record_corrected(self, kind: str, *, corrected: int) -> None:
        """Add how many seeded rows of one kind this run put right, and log it.

        A correction changes a row an earlier run of the seed wrote, when the
        seed data has since been found wrong. It never touches a row the seed
        did not write.

        Args:
            kind: The label the count is kept under.
            corrected: How many rows this run changed.

        Raises:
            ValueError: If the count is negative, which can only be a bug in
                the loader that called this.

        """
        if corrected < 0:
            raise ValueError(
                f"Attempted to record {corrected} corrected rows of kind {kind!r}. A count "
                "cannot be negative."
            )
        self.corrected[kind] = self.corrected.get(kind, 0) + corrected
        logger.info("seed.rows_corrected", extra={"kind": kind, "corrected_count": corrected})

    @property
    def total_created(self) -> int:
        """Return how many rows the run inserted across every kind."""
        return sum(self.created.values())

    @property
    def total_found(self) -> int:
        """Return how many rows the run found already present across every kind."""
        return sum(self.found.values())

    @property
    def total_corrected(self) -> int:
        """Return how many seeded rows the run put right across every kind."""
        return sum(self.corrected.values())

    @property
    def changed_nothing(self) -> bool:
        """Return True when the run inserted no row and corrected none."""
        return self.total_created == 0 and self.total_corrected == 0
