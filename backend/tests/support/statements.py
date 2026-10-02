"""Count the statements an engine is asked to run.

A query that loops in Python looks fine on three rows and falls over on three
hundred. The way to catch it is to count what actually reaches the database,
so this listens on the engine and keeps every statement text it sees. A test
then asserts that the number does not grow with the data.

Only statements sent through a cursor are seen. The driver opens and ends a
transaction without one, so those do not inflate the count.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from sqlalchemy import Engine, event

CURSOR_EVENT: Final[str] = "before_cursor_execute"


@contextmanager
def recorded_statements(engine: Engine) -> Iterator[list[str]]:
    """Yield a list that fills with every statement the engine runs meanwhile.

    Args:
        engine: The engine to listen on.

    Yields:
        The statement texts, in the order they were sent.

    """
    statements: list[str] = []

    def _record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        """Keep the text of one statement."""
        statements.append(statement)

    event.listen(engine, CURSOR_EVENT, _record)
    try:
        yield statements
    finally:
        event.remove(engine, CURSOR_EVENT, _record)


__all__ = ["recorded_statements"]
