"""How a read says which of its parameters it refused.

A read is asked with a handful of parameters, a period, a category, a branch.
When a rule refuses one of them the caller wants to know which, so a form can
put the sentence beside the input it belongs to. A read therefore refuses with
an ordinary `ValidationFailure` whose detail names the parameter under one
agreed key.

The name is the one the read itself uses for the parameter. Nothing here knows
about HTTP. The API layer reads the key and decides how the answer is shaped.

The sentence of a refusal is shown to the visitor beside the input, exactly as
it is written. So it says what to do in plain words, and the rule that refused
and the values that were tried go in `rule` and in the detail, which the API
layer writes to the log and does not send.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from app.domain.errors import DetailValue, ValidationFailure

# The member of the detail bag that names the refused parameter.
REFUSED_PARAMETER: Final[str] = "refused_parameter"


def refused(
    parameter: str,
    message: str,
    detail: Mapping[str, DetailValue] | None = None,
    *,
    rule: str | None = None,
) -> ValidationFailure:
    """Build the failure for one refused parameter.

    Args:
        parameter: The name of the parameter the rule refused.
        message: A plain sentence a visitor can act on. It is shown as written.
        detail: Further structured context for the log.
        rule: The business rule that refused, for the log.

    Returns:
        The failure to raise. It is returned and not raised here, so the call
        site can chain it to the error that caused it.

    """
    return ValidationFailure(
        message, {**(detail or {}), REFUSED_PARAMETER: parameter}, rule=rule
    )


def refused_parameter_of(failure: ValidationFailure) -> str | None:
    """Return the parameter a failure names, or None when it names none."""
    parameter = failure.detail.get(REFUSED_PARAMETER)
    return parameter if isinstance(parameter, str) else None
