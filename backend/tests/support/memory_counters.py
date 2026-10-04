"""The throttle counters of an in memory unit of work, in a dictionary.

A counter is one entry for one bucket and one window. The two in memory units
of work keep their counters in the working copy of a transaction, so a count
or a delete is kept only when the transaction commits, as it is in the table.
The real statements, the row locks and the index are proved against
PostgreSQL in tests/integration.
"""

from __future__ import annotations

from datetime import datetime

# One counter, keyed by its bucket and the start of its window.
type CounterKey = tuple[str, datetime]


class MemoryRateLimits:
    """The `RateLimitStore` port over a dictionary of counters."""

    def __init__(self, counters: dict[CounterKey, int]) -> None:
        """Bind to the counters of one working copy."""
        self._counters = counters

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        """Add one to a counter and return the new count."""
        key = (bucket_key_hash, window_started_at)
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    def delete_windows_before(self, cutoff: datetime, limit: int) -> int:
        """Delete at most `limit` counters whose window began before the cutoff, oldest first."""
        due = sorted(
            (key for key in self._counters if key[1] < cutoff), key=lambda key: (key[1], key[0])
        )[:limit]
        for key in due:
            del self._counters[key]
        return len(due)

    def total_since(self, bucket_key_hash: str, since: datetime) -> int:
        """Return the sum of the counters of a bucket whose windows began at or after `since`."""
        return sum(
            count
            for (bucket, window_started_at), count in self._counters.items()
            if bucket == bucket_key_hash and window_started_at >= since
        )


__all__ = ["CounterKey", "MemoryRateLimits"]
