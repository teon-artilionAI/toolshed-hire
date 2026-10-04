"""An administrator setting the standing of a customer (BR-18).

A customer stands ACTIVE, ON_HOLD or BLACKLISTED. The no show rule puts an
account in good standing on hold by itself, in `app.domain.no_show`, and only
an administrator lifts a hold or sets or clears a blacklisting. An
administrator may move a customer between any two of the three, and gives a
reason, which the audit event keeps beside the move.

The standing is the one thing that changes. The count of bookings the
customer did not collect stays as it was when a hold is lifted, because it
records what happened. The next no show is still counted against the twelve
months it falls in, so a customer released with three strikes in the window
is put on hold again by the next one.

A customer whose standing is not ACTIVE cannot book. That is
`CustomerProfile.ensure_may_book`, which every booking already asks, so a
standing set here takes effect on the next booking with nothing more to do.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import AccountStatus
from app.domain.override_reason import written_reason


@dataclass(frozen=True, slots=True)
class StandingChange:
    """A move of a customer's standing, with the reason the administrator gave.

    Attributes:
        before: The standing as it is.
        after: The standing asked for.
        reason: Why, trimmed, five to two hundred characters.

    """

    before: AccountStatus
    after: AccountStatus
    reason: str

    @property
    def changes_anything(self) -> bool:
        """Return True when the standing asked for is not the one the customer has."""
        return self.before is not self.after


def standing_change(current: AccountStatus, wanted: AccountStatus, reason: str) -> StandingChange:
    """Return the move from one standing to another, or refuse its reason.

    Every pairing of the three standings is allowed, the same one included,
    which changes nothing.

    Raises:
        ValidationFailure: If the reason is shorter than five characters or
            longer than two hundred once trimmed. The detail names `reason`.

    """
    return StandingChange(before=current, after=wanted, reason=written_reason(reason))
