"""Removing what identifies a customer, when they ask or two years after their last hire (#113).

POPIA lets a customer ask for their personal details to be removed, and the
privacy notice promises to remove them two years after the last hire unless the
account is still in use. Removing them means writing fixed values over every
column the personal data map names as identifying a customer, on the profile
and on the sign in account, and clearing what someone may have typed about them
into a booking, a hire or a damage report. The values are here, once, so the
request of the owner and the monthly job write the same thing.

The rows stay. A hire, its charges and its deposit are financial records kept
for five years, so they stay linked to the profile, which no longer says who it
belonged to. The audit trail is not touched either, because the application
role may only add to it (BR-49) and it is the legal record of what was done.

A customer is anonymised once, and only when nothing is left open. A booking
still to be collected, a hire not yet settled or money still owing needs the
details to be finished, so each of those refuses, in a sentence that says what
is open.

The job finds customers whose last hire ended, or whose profile was made with no
hire at all, more than two years ago, and who have not signed in for as long.
`dormancy_cutoff` is the instant both are measured against.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Final
from uuid import UUID

from app.domain.enums import CustomerType, ReservationStatus
from app.domain.errors import StateTransitionError

# The privacy notice's period, counted back from the run of the job.
DORMANT_FOR_YEARS: Final[int] = 2
# The day a leap year's 29 February becomes when the year it is moved to has none.
LEAP_DAY_MONTH: Final[int] = 2
LEAP_DAY: Final[int] = 29
DAY_BEFORE_LEAP_DAY: Final[int] = 28

# What the profile and the account hold once the customer is anonymised. Every
# value fits its column, and none of them can be mistaken for a real name, a
# number someone could ring or an address someone could visit.
ANONYMISED_DISPLAY_NAME: Final[str] = "Former customer"
ANONYMISED_TEXT: Final[str] = "Removed"
# `id_document_last4` is CHAR(4) and NOT NULL.
ANONYMISED_ID_DIGITS: Final[str] = "0000"
# The .invalid top level domain is reserved and never delivers (RFC 2606), so
# nothing the application sends can reach a person through one of these.
ANONYMISED_EMAIL_DOMAIN: Final[str] = "anonymised.invalid"
ANONYMISED_EMAIL_PREFIX: Final[str] = "former-customer"
# What a free text column that may not be null says in place of what was typed.
REMOVED_NOTE: Final[str] = "Removed when the customer was anonymised."

# A booking in one of these is still to be collected, so it is open.
OPEN_BOOKING_STATUSES: Final[tuple[ReservationStatus, ...]] = (
    ReservationStatus.DRAFT,
    ReservationStatus.HELD,
    ReservationStatus.CONFIRMED,
)

ANONYMISATION_RULE: Final[str] = "NFR-16"
ANONYMISED_STATE: Final[str] = "anonymised"
IDENTIFIED_STATE: Final[str] = "identified"
ALREADY_ANONYMISED_MESSAGE: Final[str] = (
    "This customer was anonymised already, so there is nothing left to remove."
)
SIGNED_IN_SINCE_MESSAGE: Final[str] = (
    "This customer signed in within the last two years, so the schedule leaves them be."
)
SINGLE: Final[int] = 1


class AnonymisationTrigger(str, Enum):
    """Why a customer was anonymised, which the audit event names."""

    REQUEST = "request"
    SCHEDULE = "schedule"


@dataclass(frozen=True, slots=True)
class AnonymisedProfile:
    """The values written over the identifying columns of `customer_profile`.

    Attributes:
        display_name: The name staff see.
        company_name: Kept for a trade customer, whose profile must name a
            company, and None for anyone else.
        vat_number: Always None.
        id_document_last4: Four zeros.
        contact_phone: A word, so no search by number finds it.
        billing_address_line1: A word.
        billing_suburb: A word.
        billing_city: A word.
        billing_postal_code: A word.

    """

    display_name: str
    company_name: str | None
    vat_number: str | None
    id_document_last4: str
    contact_phone: str
    billing_address_line1: str
    billing_suburb: str
    billing_city: str
    billing_postal_code: str


@dataclass(frozen=True, slots=True)
class AnonymisedAccount:
    """The values written over the identifying columns of `user_account`.

    Attributes:
        email: An address unique to the profile, at a domain that never delivers.
        full_name: The same name the profile is given.
        phone: Always None.

    """

    email: str
    full_name: str
    phone: str | None


@dataclass(frozen=True, slots=True)
class OpenMatters:
    """What a customer still has open, any of which refuses an anonymisation.

    Attributes:
        open_bookings: Bookings in DRAFT, HELD or CONFIRMED.
        unsettled_hires: Hires not yet SETTLED.
        hires_owing: Hires with a balance due or a charge still pending.

    """

    open_bookings: int = 0
    unsettled_hires: int = 0
    hires_owing: int = 0

    @property
    def is_clear(self) -> bool:
        """Return True when nothing is open."""
        return not (self.open_bookings or self.unsettled_hires or self.hires_owing)


def anonymised_email(customer_profile_id: UUID) -> str:
    """Return the address an anonymised account holds, unique because the profile key is."""
    return f"{ANONYMISED_EMAIL_PREFIX}-{customer_profile_id}@{ANONYMISED_EMAIL_DOMAIN}"


def anonymised_profile(customer_type: CustomerType) -> AnonymisedProfile:
    """Return the values the profile of a customer of this type is given."""
    keeps_a_company = customer_type is CustomerType.TRADE
    return AnonymisedProfile(
        display_name=ANONYMISED_DISPLAY_NAME,
        company_name=ANONYMISED_DISPLAY_NAME if keeps_a_company else None,
        vat_number=None,
        id_document_last4=ANONYMISED_ID_DIGITS,
        contact_phone=ANONYMISED_TEXT,
        billing_address_line1=ANONYMISED_TEXT,
        billing_suburb=ANONYMISED_TEXT,
        billing_city=ANONYMISED_TEXT,
        billing_postal_code=ANONYMISED_TEXT,
    )


def anonymised_account(customer_profile_id: UUID) -> AnonymisedAccount:
    """Return the values the sign in account of this customer is given."""
    return AnonymisedAccount(
        email=anonymised_email(customer_profile_id),
        full_name=ANONYMISED_DISPLAY_NAME,
        phone=None,
    )


def ensure_may_be_anonymised(anonymised_at: datetime | None, matters: OpenMatters) -> None:
    """Refuse a customer who was anonymised already or still has something open.

    Args:
        anonymised_at: When the customer was anonymised, or None.
        matters: What the customer still has open.

    Raises:
        StateTransitionError: Saying that the customer was anonymised already,
            or naming what is open.

    """
    if anonymised_at is not None:
        raise StateTransitionError(
            ALREADY_ANONYMISED_MESSAGE,
            from_status=ANONYMISED_STATE,
            to_status=ANONYMISED_STATE,
            rule=ANONYMISATION_RULE,
        )
    if not matters.is_clear:
        raise StateTransitionError(
            open_matters_message(matters),
            from_status=IDENTIFIED_STATE,
            to_status=ANONYMISED_STATE,
            rule=ANONYMISATION_RULE,
        )


def ensure_still_dormant(last_signed_in_at: datetime | None, cutoff: datetime) -> None:
    """Refuse a customer the schedule found whose account has signed in since the cutoff.

    Args:
        last_signed_in_at: The last sign in of the account, or when it was
            opened, or None for a walk-in, who never signs in.
        cutoff: Two years before the run of the job.

    Raises:
        StateTransitionError: If the account signed in at or after the cutoff.

    """
    if last_signed_in_at is not None and last_signed_in_at >= cutoff:
        raise StateTransitionError(
            SIGNED_IN_SINCE_MESSAGE,
            from_status=IDENTIFIED_STATE,
            to_status=ANONYMISED_STATE,
            rule=ANONYMISATION_RULE,
        )


def open_matters_message(matters: OpenMatters) -> str:
    """Return the sentence that names what a customer still has open."""
    parts = [
        _counted(matters.open_bookings, "a booking still open", "{count} bookings still open"),
        _counted(
            matters.unsettled_hires, "a hire not yet settled", "{count} hires not yet settled"
        ),
        _counted(matters.hires_owing, "money owing on a hire", "money owing on {count} hires"),
    ]
    named = [part for part in parts if part]
    listed = named[0] if len(named) == SINGLE else ", ".join(named[:-1]) + " and " + named[-1]
    return (
        f"This customer still has {listed}, so their details cannot be removed yet. "
        "Finish what is open first."
    )


def _counted(count: int, one: str, many: str) -> str:
    """Return the words for a count of something open, or nothing when there is none."""
    if count <= 0:
        return ""
    return one if count == SINGLE else many.format(count=count)


def dormancy_cutoff(now: datetime) -> datetime:
    """Return the instant two years before now, which the job measures dormancy against.

    The years are calendar years, so 29 February moves to 28 February in a
    year that has no leap day.
    """
    year = now.year - DORMANT_FOR_YEARS
    if (now.month, now.day) == (LEAP_DAY_MONTH, LEAP_DAY):
        try:
            return now.replace(year=year)
        except ValueError:
            return now.replace(year=year, day=DAY_BEFORE_LEAP_DAY)
    return now.replace(year=year)
