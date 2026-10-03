"""The small rules the account use cases share.

An email address is compared in one form, lower case with no space around it.

A refusal names its field the way the request did. The domain names a field
in its own words, for example `billing_city`, and a form needs `billingCity`
to put the sentence beside the right input. `refused_field` turns one into
the other, and `ensure_password_may_be_set` does the same for the password
rule, which is asked about under two different names.
"""

from __future__ import annotations

from typing import Final

from app.application.refusal import refused
from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import ValidationFailure
from app.domain.password_policy import ensure_password_may_be_chosen

WORD_SEPARATOR: Final[str] = "_"


def normalised_email(email: str) -> str:
    """Return an email address in the one form two of them are compared in."""
    return email.strip().lower()


def wire_name(field: str) -> str:
    """Return the name a domain field has in a request, for example `billingCity`."""
    first, *rest = field.split(WORD_SEPARATOR)
    return first + "".join(word.capitalize() for word in rest)


def refused_field(failure: ValidationFailure) -> ValidationFailure:
    """Return the refusal of a field the domain refused, named as the request named it.

    Args:
        failure: A failure whose detail names the field under `REFUSED_FIELD`.

    """
    field = str(failure.detail[REFUSED_FIELD])
    return refused(wire_name(field), failure.message, rule=failure.rule)


def ensure_password_may_be_set(plain_password: str, parameter: str) -> None:
    """Refuse a chosen password that breaks the password rule, naming its field (BR-45).

    Args:
        plain_password: The password as it was typed. Never logged.
        parameter: The name the password has in the request.

    Raises:
        ValidationFailure: If the password is too short or too long. The
            detail names the parameter.

    """
    try:
        ensure_password_may_be_chosen(plain_password)
    except ValidationFailure as failure:
        raise refused(parameter, failure.message, failure.detail, rule=failure.rule) from failure
