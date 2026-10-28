"""The port the anonymisation of a customer writes through, and what it reads and returns (#113).

Anonymising a customer touches the profile, the account, the refresh sessions
and the customer's own bookings, hires, damage reports, charges and
notifications. It is one port over all of them, because it is one change and
the personal data map, which says where the columns are, belongs to the
infrastructure layer that implements it.

The same port finds the customers the monthly job anonymises, a page at a time
in the order of their key, so a job that stops part way can start again from
the last key it logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.anonymisation import AnonymisedAccount, AnonymisedProfile, OpenMatters
from app.domain.enums import CustomerType


@dataclass(frozen=True, slots=True)
class ErasureSubject:
    """A customer about to be anonymised, read under a row lock.

    Attributes:
        customer_profile_id: The profile.
        user_account_id: The sign in account, or None for a walk-in.
        customer_type: Whether they hire as an individual or as a trade.
        anonymised_at: When they were anonymised, or None.
        last_signed_in_at: The last sign in of the account, or when it was
            opened if it never signed in. None for a walk-in.

    """

    customer_profile_id: UUID
    user_account_id: UUID | None
    customer_type: CustomerType
    anonymised_at: datetime | None
    last_signed_in_at: datetime | None


@dataclass(frozen=True, slots=True)
class ErasedRows:
    """How many rows of each kind an anonymisation wrote over.

    Attributes:
        sessions: Refresh sessions whose browser and address were cleared.
        bookings: Bookings whose notes and cancellation reason were cleared.
        hire_items: Units on a hire whose notes were cleared.
        damage_reports: Damage reports whose description and notes were replaced.
        charges: Charges whose waiver reason was replaced.
        notifications: Notifications whose recipient and last error were replaced.

    """

    sessions: int = 0
    bookings: int = 0
    hire_items: int = 0
    damage_reports: int = 0
    charges: int = 0
    notifications: int = 0


class PersonalDataEraser(Protocol):
    """Where a customer's personal details are read for, and written over."""

    def subject_for_update(self, customer_profile_id: UUID) -> ErasureSubject | None:
        """Return the customer, with the profile and the account locked, or None when unknown."""
        ...

    def open_matters(self, customer_profile_id: UUID) -> OpenMatters:
        """Return the bookings, hires and money the customer still has open."""
        ...

    def erase(
        self,
        subject: ErasureSubject,
        *,
        profile: AnonymisedProfile,
        account: AnonymisedAccount | None,
        at: datetime,
    ) -> ErasedRows:
        """Write the anonymised values over the customer's rows and stamp the profile.

        Args:
            subject: The customer, as `subject_for_update` read them.
            profile: What the profile's identifying columns become.
            account: What the account's identifying columns become, or None
                for a walk-in. The account is also made inactive.
            at: When, which the profile keeps as `anonymised_at`.

        """
        ...

    def dormant_customers(
        self, cutoff: datetime, *, after: UUID | None, limit: int
    ) -> tuple[UUID, ...]:
        """Return the next customers the monthly job may anonymise, in the order of their key.

        A customer qualifies when they are not anonymised, their profile was
        made before `cutoff`, their account, if they have one, has not signed
        in since `cutoff`, no booking of theirs is open or was made since
        `cutoff`, and every hire of theirs is settled, owes nothing and ended
        before `cutoff`.

        Args:
            cutoff: Two years before the run.
            after: The last key of the previous page, or None for the first.
            limit: The most keys to return.

        """
        ...
