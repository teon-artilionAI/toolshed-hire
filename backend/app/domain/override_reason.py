"""The reason an administrator gives for overriding what the system recorded (BR-25, US-32).

Waiving, reversing and adjusting a charge, and forcing the release of a unit
held for a booking, are the manual escape hatches of the office. Each one is
written to the audit log with the reason and the actor (BR-25), so the log can
say later who did it and why. A reason is therefore required, and it has to be
long enough to say something and short enough for the column a waiver keeps
it in.

The API checks the length as well, so a form is told which field was wrong. It
is checked here too, because the rule is the domain's and a caller other than
the API must not get round it.
"""

from __future__ import annotations

from typing import Final

from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import ValidationFailure

REASON_MIN_LENGTH: Final[int] = 5
# The width of `charge.waiver_reason`, where the reason of a correction is kept.
REASON_MAX_LENGTH: Final[int] = 200
REASON_FIELD: Final[str] = "reason"
OVERRIDE_REASON_RULE: Final[str] = "BR-25"
REASON_LENGTH_MESSAGE: Final[str] = (
    f"Give a reason of {REASON_MIN_LENGTH} to {REASON_MAX_LENGTH} characters."
)


def written_reason(reason: str) -> str:
    """Return the reason as it is kept, trimmed of surrounding space, or refuse it.

    Args:
        reason: What the administrator typed.

    Raises:
        ValidationFailure: If it is shorter than five characters or longer than
            two hundred once trimmed. The detail names the field.

    """
    written = reason.strip()
    if not REASON_MIN_LENGTH <= len(written) <= REASON_MAX_LENGTH:
        raise ValidationFailure(
            REASON_LENGTH_MESSAGE,
            {REFUSED_FIELD: REASON_FIELD, "length": len(written)},
            rule=OVERRIDE_REASON_RULE,
        )
    return written
