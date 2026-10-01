"""The one error the loader raises about its own input."""

from __future__ import annotations


class SeedDataError(ValueError):
    """Raised when the seed data cannot be loaded as it is written.

    I raise it before anything is written wherever I can, so a mistake in the
    data package stops the run with a sentence that names the row, instead of
    surfacing later as a constraint violation half way through a transaction.
    """
