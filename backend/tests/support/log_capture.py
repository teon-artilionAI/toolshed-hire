"""Read what the application really wrote to its log.

A test that inspects LogRecord objects proves what was passed to the logger. It
does not prove what reached the log, because the request id and the redaction
are applied by filters on the application's handler, and a record captured by
any other handler never passed through them.

So this builds the application's own handler, with its formatter and both of
its filters, over an in memory stream, attaches it to the root logger the way
`configure_logging` does, and parses the JSON lines that come out. What a test
reads here is byte for byte what Cloud Logging would have been sent.

`preserved_logging_configuration` is here for the same reason. The Alembic
environment installs the logging configuration from alembic.ini, which raises
the root level to WARNING and switches off every logger that already exists.
That suits the command line, where the process ends with the migration. Inside
a test session it would silence the application for every test that runs
afterwards, so the migration fixture puts the configuration back.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Final

from app.logging_config import build_handler

APPLICATION_LOGGER_PREFIX: Final[str] = "app."


@dataclass
class LogCapture:
    """The log lines written while the capture was attached."""

    stream: io.StringIO = field(default_factory=io.StringIO)

    @property
    def text(self) -> str:
        """Return the raw output, exactly as it was written."""
        return self.stream.getvalue()

    def entries(self) -> list[dict[str, object]]:
        """Return every line parsed back from JSON, in the order written."""
        return [json.loads(line) for line in self.text.splitlines() if line.strip()]

    def application_entries(self) -> list[dict[str, object]]:
        """Return the lines written by the application's own modules.

        The HTTP client the tests use logs each call it makes, from outside the
        request, and those lines say nothing about the application.
        """
        return [
            entry
            for entry in self.entries()
            if str(entry["logger"]).startswith(APPLICATION_LOGGER_PREFIX)
        ]

    def named(self, message: str) -> list[dict[str, object]]:
        """Return the lines whose message is exactly `message`."""
        return [entry for entry in self.entries() if entry["message"] == message]

    def only(self, message: str) -> dict[str, object]:
        """Return the single line with this message, failing if there is not one."""
        matches = self.named(message)
        assert len(matches) == 1, (
            f"Expected exactly one {message!r} line and found {len(matches)}. "
            f"The messages written were {[entry['message'] for entry in self.entries()]}."
        )
        return matches[0]

    def clear(self) -> None:
        """Forget everything written so far."""
        self.stream.seek(0)
        self.stream.truncate()


@contextmanager
def capture_application_log() -> Iterator[LogCapture]:
    """Attach the application's real handler to the root logger for a while.

    Yields:
        The capture, which fills as the application logs.

    """
    capture = LogCapture()
    handler = build_handler(capture.stream)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield capture
    finally:
        root.removeHandler(handler)


@contextmanager
def preserved_logging_configuration() -> Iterator[None]:
    """Put the logging configuration back as it was when the block ends.

    The root level, the root handlers and the disabled flag of every logger
    that existed on entry are restored. Loggers created inside the block are
    left as they are.
    """
    root = logging.getLogger()
    level = root.level
    handlers = list(root.handlers)
    disabled = {
        name: existing.disabled
        for name, existing in logging.Logger.manager.loggerDict.items()
        if isinstance(existing, logging.Logger)
    }
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)
        for name, was_disabled in disabled.items():
            logging.getLogger(name).disabled = was_disabled


__all__ = ["LogCapture", "capture_application_log", "preserved_logging_configuration"]
