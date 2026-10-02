"""Plain sentences for the query parameters the framework refuses.

A read takes its parameters from the query string, and the framework checks
their types and their ranges before any rule of mine runs. When it refuses one
it writes a sentence of its own, for example "Input should be a valid date or
datetime, input is too short". That sentence is put beside an input on a
customer's screen exactly as it is written, so it is replaced here with one
that says what to do.

The replacement is chosen by the kind of refusal, which the framework names,
and never by reading its sentence. A kind with no sentence of its own here is
answered with a general one, so nothing the framework wrote can reach the
screen by being new.

Only query parameters are reworded. A request body is refused in the
framework's own words, as before.

What the framework refused, by its kind, goes to the log. The value that was
sent does not, because a search text is among the values and it is never
logged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

QUERY_LOCATION: Final[str] = "query"
BODY_LOCATION: Final[str] = "body"
LOCATION_SEPARATOR: Final[str] = "."
SINGLE: Final[int] = 1

REQUIRED_MESSAGE: Final[str] = "This is needed. Please fill it in."
DATE_MESSAGE: Final[str] = "Enter a valid date, in the form YYYY-MM-DD."
WHOLE_NUMBER_MESSAGE: Final[str] = "Enter a whole number."
CHOICE_MESSAGE: Final[str] = "Choose one of the options offered."
NOT_ACCEPTED_MESSAGE: Final[str] = "This value was not accepted."

# The kinds of refusal the framework names, grouped by the sentence they get.
MISSING_KINDS: Final[frozenset[str]] = frozenset({"missing"})
DATE_KINDS: Final[frozenset[str]] = frozenset(
    {"date_type", "date_parsing", "date_from_datetime_parsing", "date_from_datetime_inexact"}
)
WHOLE_NUMBER_KINDS: Final[frozenset[str]] = frozenset(
    {"int_type", "int_parsing", "int_parsing_size", "int_from_float"}
)
CHOICE_KINDS: Final[frozenset[str]] = frozenset({"enum", "literal_error"})
AT_LEAST_KIND: Final[str] = "greater_than_equal"
AT_MOST_KIND: Final[str] = "less_than_equal"
TOO_SHORT_KIND: Final[str] = "string_too_short"
TOO_LONG_KIND: Final[str] = "string_too_long"

FIXED_SENTENCES: Final[tuple[tuple[frozenset[str], str], ...]] = (
    (MISSING_KINDS, REQUIRED_MESSAGE),
    (DATE_KINDS, DATE_MESSAGE),
    (WHOLE_NUMBER_KINDS, WHOLE_NUMBER_MESSAGE),
    (CHOICE_KINDS, CHOICE_MESSAGE),
)
# A kind whose sentence states a limit, with the name the framework gives the
# limit and the sentence it is written into.
LIMIT_SENTENCES: Final[Mapping[str, tuple[str, str]]] = {
    AT_LEAST_KIND: ("ge", "Enter {limit} or more."),
    AT_MOST_KIND: ("le", "Enter {limit} or less."),
    TOO_SHORT_KIND: ("min_length", "Enter at least {limit}."),
    TOO_LONG_KIND: ("max_length", "Enter at most {limit}."),
}
LENGTH_KINDS: Final[frozenset[str]] = frozenset({TOO_SHORT_KIND, TOO_LONG_KIND})


def _characters_in_words(count: object) -> str:
    """Return a number of characters as a visitor reads it."""
    return f"{count} character" if count == SINGLE else f"{count} characters"


def plain_query_message(kind: str, limits: Mapping[str, object]) -> str:
    """Return the sentence shown for one refused query parameter.

    Args:
        kind: The kind of refusal, as the framework names it.
        limits: The limits the framework says were broken, by name.

    """
    for kinds, sentence in FIXED_SENTENCES:
        if kind in kinds:
            return sentence
    if kind in LIMIT_SENTENCES:
        limit_name, sentence = LIMIT_SENTENCES[kind]
        limit = limits.get(limit_name)
        if limit is not None:
            shown = _characters_in_words(limit) if kind in LENGTH_KINDS else str(limit)
            return sentence.format(limit=shown)
    return NOT_ACCEPTED_MESSAGE


def refused_fields(
    errors: Sequence[Mapping[str, object]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Read the framework's refusals into a sentence and a kind for each field.

    Args:
        errors: The refusals of one request, as the framework reports them.

    Returns:
        Two dictionaries keyed by where the value came from and its name on
        the wire, for example `query.from`. The first holds the sentence for
        the response. The second holds the kind of refusal, for the log.

    """
    sentences: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for error in errors:
        location = error.get("loc", ())
        parts = [str(part) for part in location] if isinstance(location, Sequence) else []
        name = LOCATION_SEPARATOR.join(parts)
        kind = str(error.get("type", ""))
        context = error.get("ctx")
        limits = context if isinstance(context, Mapping) else {}
        kinds[name] = kind
        if parts[:1] == [QUERY_LOCATION]:
            sentences[name] = plain_query_message(kind, limits)
        else:
            sentences[name] = str(error.get("msg", ""))
    return sentences, kinds
