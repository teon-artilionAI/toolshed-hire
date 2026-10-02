"""Move the reference sequences past the numbers the seed has used.

A reference such as TSH-R-26-000123 ends in a number drawn from a sequence. The
seed writes its references by hand, so each sequence has to be left pointing
beyond the highest number written, or the first real booking would collide
with the worked example.

The schema holds one of these sequences today, the one behind reservation
references. Rentals and damage reports will each need one when their flows are
built. I list all three here by the name the existing one sets as the pattern,
and a sequence that does not exist yet is logged and skipped, so this step
starts working for the other two the day their migration creates them.

A sequence is only ever moved forward. One that is already past the seeded
number is left where it is, which is what keeps a second run from changing
anything and stops a run against a live database from rewinding the counter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlmodel import Session

from app.infrastructure.schema_ddl import REFERENCE_SEQUENCE
from seeding import worked_example as example
from seeding.errors import SeedDataError
from seeding.report import SeedTally

logger = logging.getLogger("seed")

SEQUENCE_KIND = "reference_sequence"
REFERENCE_SEPARATOR: Final[str] = "-"
# No damage report is seeded, so any starting number is already past the seed.
NO_SEEDED_NUMBER: Final[int] = 0


@dataclass(frozen=True, slots=True)
class ReferenceSequence:
    """One sequence and the highest number the seed wrote by hand from its range."""

    name: str
    highest_seeded_number: int

    @property
    def minimum_next_value(self) -> int:
        """Return the lowest number the sequence may hand out next."""
        return self.highest_seeded_number + 1


def number_of(reference: str) -> int:
    """Return the trailing number of a reference, for example 123 for TSH-R-26-000123.

    Raises:
        SeedDataError: If the reference does not end in digits after a hyphen.

    """
    trailing = reference.rsplit(REFERENCE_SEPARATOR, 1)[-1]
    if not trailing.isdigit():
        raise SeedDataError(
            f"Reference {reference!r} does not end in a number, so I cannot tell which "
            "sequence value it used."
        )
    return int(trailing)


REFERENCE_SEQUENCES: Final[tuple[ReferenceSequence, ...]] = (
    ReferenceSequence(REFERENCE_SEQUENCE, number_of(example.RESERVATION_REFERENCE)),
    ReferenceSequence("rental_reference_seq", number_of(example.RENTAL_REFERENCE)),
    ReferenceSequence("damage_report_reference_seq", NO_SEEDED_NUMBER),
)


def advance_reference_sequences(session: Session, tally: SeedTally) -> None:
    """Leave every reference sequence that exists past its seeded number."""
    advanced = 0
    already_past = 0
    for sequence in REFERENCE_SEQUENCES:
        next_value = _next_value(session, sequence.name)
        if next_value is None:
            logger.info(
                "seed.sequence_absent",
                extra={
                    "sequence": sequence.name,
                    "action": "skipped, the schema does not create this sequence yet",
                },
            )
            continue
        if next_value >= sequence.minimum_next_value:
            already_past += 1
            logger.debug(
                "seed.sequence_already_past",
                extra={"sequence": sequence.name, "next_value": next_value},
            )
            continue
        # Marked as called at the seeded number, so the next value drawn is the
        # one after it and the catalogue reports the position on the next run.
        session.execute(
            text("SELECT setval(CAST(:name AS regclass), :value, true)"),
            {"name": sequence.name, "value": sequence.highest_seeded_number},
        )
        advanced += 1
        logger.info(
            "seed.sequence_advanced",
            extra={
                "sequence": sequence.name,
                "was_next": next_value,
                "now_next": sequence.minimum_next_value,
            },
        )
    tally.record(SEQUENCE_KIND, created=advanced, found=already_past)


def _next_value(session: Session, sequence_name: str) -> int | None:
    """Return the value a sequence would hand out next, or None if it does not exist.

    Read from the catalogue view, so the sequence name travels as a bound value
    and is never written into the statement. `last_value` is null until the
    sequence has been drawn from, and then the next value is its start.
    """
    row = session.execute(
        text(
            "SELECT last_value, start_value, increment_by FROM pg_sequences "
            "WHERE schemaname = current_schema() AND sequencename = :name"
        ),
        {"name": sequence_name},
    ).first()
    if row is None:
        return None
    last_value, start_value, increment_by = row
    if last_value is None:
        return int(start_value)
    return int(last_value) + int(increment_by)
