"""Counting days over half open spans, which is the arithmetic of the utilisation report.

Every span here is `[begins, ends)`, the same half open rule as a hire period
and the exclusion constraint (BR-02). A unit back on the twelfth is on hire on
the eleventh and not on the twelfth, so two spans that meet on a day share no
day, and a span whose two ends are the same day holds nothing.

A unit can be out of service for two reasons at once, for example quarantined
by a return and named by a damage report the next morning. Counting each
reason on its own would take those days off twice. So spans are only ever
counted once they have been joined into a union, where every day is in at most
one span, and `days_in` counts that union. Nothing else in the application
counts the days of a span.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True, order=True)
class DaySpan:
    """A run of whole days, from `begins` up to but not including `ends`.

    Attributes:
        begins: The first day in the span.
        ends: The first day after it.

    """

    begins: date
    ends: date

    def __post_init__(self) -> None:
        """Refuse a span that ends before it begins.

        Raises:
            ValueError: If `ends` is before `begins`.

        """
        if self.ends < self.begins:
            raise ValueError(
                f"Attempted to build a span of days from {self.begins.isoformat()} to "
                f"{self.ends.isoformat()}, which ends before it begins."
            )

    @property
    def length(self) -> int:
        """Return how many days the span holds."""
        return (self.ends - self.begins).days

    def clipped_to(self, window: DaySpan) -> DaySpan | None:
        """Return the part of this span inside the window, or None when they share no day."""
        begins = max(self.begins, window.begins)
        ends = min(self.ends, window.ends)
        return DaySpan(begins, ends) if begins < ends else None


def span_or_none(begins: date, ends: date) -> DaySpan | None:
    """Return the span between two days, or None when it would hold no day."""
    return DaySpan(begins, ends) if begins < ends else None


def merged(spans: Iterable[DaySpan | None]) -> tuple[DaySpan, ...]:
    """Return the union of some spans, in order, with no two sharing or touching a day.

    A span that holds no day, and a None, are left out. Spans that overlap or
    meet end to start are joined into one.
    """
    union: list[DaySpan] = []
    for span in sorted(span for span in spans if span is not None and span.length):
        if union and span.begins <= union[-1].ends:
            last = union[-1]
            union[-1] = DaySpan(last.begins, max(last.ends, span.ends))
        else:
            union.append(span)
    return tuple(union)


def days_in(spans: Iterable[DaySpan | None]) -> int:
    """Return how many distinct days the spans hold between them, each day once."""
    return sum(span.length for span in merged(spans))


def clipped(spans: Iterable[DaySpan | None], window: DaySpan | None) -> tuple[DaySpan, ...]:
    """Return the union of the spans, cut to the window. Nothing when there is no window."""
    if window is None:
        return ()
    return merged(span.clipped_to(window) for span in merged(spans))


def overlap(
    first: Iterable[DaySpan | None], second: Iterable[DaySpan | None]
) -> tuple[DaySpan, ...]:
    """Return the days that are in both sets of spans, as a union."""
    others = merged(second)
    return merged(span.clipped_to(other) for span in merged(first) for other in others)


def without(
    spans: Iterable[DaySpan | None], removed: Iterable[DaySpan | None]
) -> tuple[DaySpan, ...]:
    """Return the days of the spans that are not in any removed span, as a union."""
    remaining = list(merged(spans))
    for cut in merged(removed):
        pieces: list[DaySpan | None] = []
        for span in remaining:
            if span.clipped_to(cut) is None:
                pieces.append(span)
                continue
            pieces.append(span_or_none(span.begins, cut.begins))
            pieces.append(span_or_none(cut.ends, span.ends))
        remaining = list(merged(pieces))
    return tuple(remaining)
