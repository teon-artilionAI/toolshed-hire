"""The forms the text of the catalogue takes, shared by a category and a model.

A category and a model are both named three ways. A code, or a SKU for a
model, is what staff read out and print on paperwork, so it is capital letters
and digits in words joined by single hyphens, for example `BREAK-DRILL` or
`DR-BOSCH-GBH226`. A slug is what the model or the category is called in an
address, so it is small letters and digits joined the same way, for example
`breaking-drilling`. A name is free text. Each has the width of the column it
is stored in, which is the width the design document gives it.

Every value is trimmed before it is checked. Required text that is blank once
trimmed is refused, and optional text that is blank is kept as nothing.

A refusal names its field the way this layer names it, for example
`short_description`, under `REFUSED_FIELD`, and says what to do in a sentence
that is shown beside the input as it is written.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Final

from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import ValidationFailure
from app.domain.money import ONE_CENT

# Words of capital letters and digits joined by single hyphens, for a code or a SKU.
CODE_FORM: Final[re.Pattern[str]] = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*")
# Words of small letters and digits joined by single hyphens, for a slug.
SLUG_FORM: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# The largest amount a NUMERIC(12,2) column holds.
LARGEST_AMOUNT: Final[Decimal] = Decimal("9999999999.99")
NO_AMOUNT: Final[Decimal] = Decimal("0")

REQUIRED_MESSAGE: Final[str] = "This is needed. Please fill it in."
TOO_LONG_MESSAGE: Final[str] = "Enter at most {limit} characters."
CODE_FORM_MESSAGE: Final[str] = (
    "Use capital letters and digits, with a single hyphen between words, for example DRILL-SDS."
)
SLUG_FORM_MESSAGE: Final[str] = (
    "Use small letters and digits, with a single hyphen between words, for example "
    "rotary-hammers."
)
NOT_AN_AMOUNT_MESSAGE: Final[str] = "Enter an amount in rand, for example 280.00."
BELOW_ZERO_MESSAGE: Final[str] = "Enter an amount of zero or more."
PART_OF_A_CENT_MESSAGE: Final[str] = (
    "Enter the amount in rand and cents, with at most two decimals."
)
TOO_LARGE_MESSAGE: Final[str] = "Enter an amount of at most R9,999,999,999.99."
# Every amount is held exactly and is never below zero (BR-22).
MONEY_RULE: Final[str] = "BR-22"


def field_refusal(field: str, message: str, *, rule: str | None = None) -> ValidationFailure:
    """Return the failure for one refused field of the catalogue.

    Args:
        field: The field, named the way this layer names it.
        message: A plain sentence the administrator can act on.
        rule: The business rule that refused, for the log.

    """
    return ValidationFailure(message, {REFUSED_FIELD: field}, rule=rule)


def required_text(field: str, value: str, max_length: int) -> str:
    """Return the text trimmed, or refuse it when it is blank or too wide for its column.

    Raises:
        ValidationFailure: Naming the field.

    """
    trimmed = value.strip()
    if not trimmed:
        raise field_refusal(field, REQUIRED_MESSAGE)
    if len(trimmed) > max_length:
        raise field_refusal(field, TOO_LONG_MESSAGE.format(limit=max_length))
    return trimmed


def optional_text(field: str, value: str | None, max_length: int | None) -> str | None:
    """Return the text trimmed, None when it is blank, or refuse it when it is too wide.

    Args:
        field: The field, named the way this layer names it.
        value: The text as it was given, or None.
        max_length: The width of the column, or None for a column of any length.

    Raises:
        ValidationFailure: Naming the field.

    """
    trimmed = (value or "").strip()
    if not trimmed:
        return None
    if max_length is not None and len(trimmed) > max_length:
        raise field_refusal(field, TOO_LONG_MESSAGE.format(limit=max_length))
    return trimmed


def code_text(field: str, value: str, max_length: int) -> str:
    """Return a code or a SKU trimmed, or refuse one that is blank, too wide or not of its form.

    Raises:
        ValidationFailure: Naming the field.

    """
    trimmed = required_text(field, value, max_length)
    if CODE_FORM.fullmatch(trimmed) is None:
        raise field_refusal(field, CODE_FORM_MESSAGE)
    return trimmed


def slug_text(field: str, value: str, max_length: int) -> str:
    """Return a slug trimmed, or refuse one that is blank, too wide or not of its form.

    Raises:
        ValidationFailure: Naming the field.

    """
    trimmed = required_text(field, value, max_length)
    if SLUG_FORM.fullmatch(trimmed) is None:
        raise field_refusal(field, SLUG_FORM_MESSAGE)
    return trimmed


def amount_held(field: str, amount: Decimal) -> Decimal:
    """Return an amount of money the catalogue may hold, or refuse it.

    An amount is a number, zero or more, no larger than its NUMERIC(12,2)
    column holds, and in whole cents (BR-22). The size is checked before the
    cents, so an absurd amount is never rounded.

    Raises:
        ValidationFailure: Naming the field.

    """
    if not amount.is_finite():
        raise field_refusal(field, NOT_AN_AMOUNT_MESSAGE, rule=MONEY_RULE)
    if amount < NO_AMOUNT:
        raise field_refusal(field, BELOW_ZERO_MESSAGE, rule=MONEY_RULE)
    if amount > LARGEST_AMOUNT:
        raise field_refusal(field, TOO_LARGE_MESSAGE, rule=MONEY_RULE)
    if amount != amount.quantize(ONE_CENT):
        raise field_refusal(field, PART_OF_A_CENT_MESSAGE, rule=MONEY_RULE)
    return amount.quantize(ONE_CENT)
