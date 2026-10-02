"""Secret removal for log records, the control the design document calls C-42.

A log is kept for a long time and read by more people than the database is, so
a credential that reaches it has effectively been published. Care at every call
site is not a control, because one careless `extra` undoes it. This filter is
attached to the log handler instead, so every record passes through it before
the formatter sees it, whichever module wrote it.

Two rules are applied.

1. An `extra` key whose name contains one of `SENSITIVE_KEY_FRAGMENTS` has its
   value replaced by `REDACTED_PLACEHOLDER`, at any depth of nesting. The match
   is on the name and ignores case, so `refresh_cookie`, `Authorization` and
   `DATABASE_URL` are all caught.
2. A connection string of the form `scheme://user:password@host` has its
   password replaced wherever it appears, in the message, in a format argument
   or in any value. The host and the user stay, because they are what a person
   reading the log needs to find the database.

The price of matching on the name is that a harmless key such as a token
lifetime is redacted too. I accept that and name such keys differently, rather
than keep a list of exceptions that someone would have to get right every time.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Final

REDACTED_PLACEHOLDER: Final[str] = "[REDACTED]"

SENSITIVE_KEY_FRAGMENTS: Final[tuple[str, ...]] = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "database_url",
)

# scheme://user:password@host. The password stops at the first "@", "/" or
# white space, so a port number in an ordinary address is never mistaken for
# one. A password holding either character has to be percent encoded to be a
# valid address in the first place.
_CONNECTION_STRING_PASSWORD: Final[re.Pattern[str]] = re.compile(
    r"(?P<lead>[a-z][a-z0-9+.\-]*://[^\s/:@]*:)[^\s/@]+(?=@)",
    re.IGNORECASE,
)
_CONNECTION_STRING_REPLACEMENT: Final[str] = rf"\g<lead>{REDACTED_PLACEHOLDER}"

# How deep a nested value is walked. A log value is a few levels at most. The
# limit exists so a structure that contains itself cannot recurse without end.
# Whatever lies below it is replaced whole, because turning it into text
# instead would write out the very keys the walk had not reached yet.
MAXIMUM_NESTING_DEPTH: Final[int] = 8
NESTING_LIMIT_PLACEHOLDER: Final[str] = "[NESTED TOO DEEPLY]"


def is_sensitive_key(name: str) -> bool:
    """Return True when a key name marks its value as a secret."""
    lowered = name.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def scrub_text(text: str) -> str:
    """Return `text` with the password of every connection string replaced."""
    return _CONNECTION_STRING_PASSWORD.sub(_CONNECTION_STRING_REPLACEMENT, text)


def scrub_value(value: object, depth: int = 0) -> object:
    """Return a copy of a log value that is safe to write.

    Mappings and sequences are walked, so a secret nested inside a `detail`
    dictionary is treated the same as one at the top. Anything that is not a
    plain JSON value is turned into its text here, which is what the formatter
    would do with it anyway, so that the text is scrubbed as well.

    Args:
        value: The value passed through `extra` or as a format argument.
        depth: How far down a nested value this call is.

    """
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return scrub_text(value)
    if not isinstance(value, Mapping | list | tuple | set | frozenset):
        return scrub_text(str(value))
    if depth >= MAXIMUM_NESTING_DEPTH:
        return NESTING_LIMIT_PLACEHOLDER
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED_PLACEHOLDER
            if is_sensitive_key(str(key))
            else scrub_value(item, depth + 1)
            for key, item in value.items()
        }
    return [scrub_value(item, depth + 1) for item in value]


class RedactionFilter(logging.Filter):
    """Remove secrets from a record before any formatter reads it."""

    def __init__(self, standard_record_keys: frozenset[str]) -> None:
        """Create the filter.

        Args:
            standard_record_keys: The attributes every LogRecord carries. Any
                other attribute arrived through `extra` and is scrubbed.

        """
        super().__init__()
        self._standard_record_keys = standard_record_keys

    def filter(self, record: logging.LogRecord) -> bool:
        """Scrub the record in place and always let it through."""
        self._scrub_message(record)
        for key, value in list(record.__dict__.items()):
            if key in self._standard_record_keys or key.startswith("_"):
                continue
            record.__dict__[key] = (
                REDACTED_PLACEHOLDER if is_sensitive_key(key) else scrub_value(value)
            )
        return True

    @staticmethod
    def _scrub_message(record: logging.LogRecord) -> None:
        """Replace the message and its arguments with the scrubbed final text.

        The arguments are merged first, because a connection string can be
        assembled from several of them and only the finished text shows it.
        """
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError):
            # The format string and its arguments do not fit together. I leave
            # the report of that fault to the handler, which prints the message
            # and the arguments, so both are scrubbed where they stand.
            record.msg = scrub_text(str(record.msg))
            if isinstance(record.args, Mapping):
                record.args = {str(key): scrub_value(item) for key, item in record.args.items()}
            elif record.args:
                record.args = tuple(scrub_value(item) for item in record.args)
            return
        record.msg = scrub_text(message)
        record.args = None


__all__ = [
    "MAXIMUM_NESTING_DEPTH",
    "NESTING_LIMIT_PLACEHOLDER",
    "REDACTED_PLACEHOLDER",
    "SENSITIVE_KEY_FRAGMENTS",
    "RedactionFilter",
    "is_sensitive_key",
    "scrub_text",
    "scrub_value",
]
