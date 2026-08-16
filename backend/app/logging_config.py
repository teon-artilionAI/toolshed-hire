"""Structured JSON logging.

Cloud Run reads stdout and parses each line as JSON when it is one, so the
formatter emits a single JSON object per record. The `severity` and `message`
keys are the ones Cloud Logging promotes, and everything passed through the
`extra` argument is merged into the same object rather than being flattened
into the message string. That is what makes a log searchable by asset tag or
reservation reference later.

There are no print statements anywhere in the application. A print has no
level, no timestamp and no structure, so it is invisible to any query.

One rule applies at every call site. A key passed through `extra` may not be
one of the names LogRecord already owns, listed in RESERVED_RECORD_KEYS below.
The standard library raises KeyError rather than overwriting, so `extra={"name":
branch.name}` fails at runtime. Use a qualified key such as `branch_name`.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Final

# Attributes LogRecord always carries. Anything else on the record arrived
# through `extra` and is therefore application context worth emitting.
_STANDARD_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "taskName", "thread", "threadName",
    }
)

# Passing any of these through `extra` raises KeyError inside logging itself.
# Kept as a named constant so the rule is discoverable rather than folklore.
RESERVED_RECORD_KEYS: Final[frozenset[str]] = _STANDARD_RECORD_KEYS | {"message", "asctime"}

SEVERITY_BY_LEVEL: Final[dict[int, str]] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

# Uvicorn's access log duplicates what the application already records and is
# noisy at request volume, so it is left at WARNING.
ACCESS_LOGGER_NAME = "uvicorn.access"


class JsonFormatter(logging.Formatter):
    """Render a log record as one JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a JSON string, including any `extra` fields."""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": SEVERITY_BY_LEVEL.get(record.levelno, record.levelname),
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger.

    Args:
        level: The threshold for the root logger. Handlers already attached are
            replaced, so calling this twice does not double every line.

    """
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger(ACCESS_LOGGER_NAME).setLevel(logging.WARNING)
    logging.getLogger(__name__).info(
        "logging.configured",
        extra={"level": logging.getLevelName(level), "format": "json"},
    )
