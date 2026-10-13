"""An in memory unit of work for the anonymisation of customers (#113).

It holds the customers by key, with what each one still has open, and keeps
what the use cases write, the anonymised values, the revoked sessions and the
audit events, only when they commit. The page of dormant customers is the keys
the test marks as dormant, in key order. The SQL behind each of these is
proved against PostgreSQL in tests/integration.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID

from app.application.identity.anonymisation_ports import ErasedRows, ErasureSubject
from app.application.identity.customer_directory import CustomerSummary
from app.domain.anonymisation import AnonymisedAccount, AnonymisedProfile, OpenMatters
from app.domain.audit import AuditEvent
from app.domain.enums import AccountStatus, CustomerType, IdDocType, RevokeReason

ERASED_ROWS = ErasedRows(sessions=2, bookings=1, hire_items=1)


@dataclass
class Known:
    """One customer as the store knows them."""

    subject: ErasureSubject
    matters: OpenMatters = field(default_factory=OpenMatters)
    profile: AnonymisedProfile | None = None
    account: AnonymisedAccount | None = None


@dataclass
class AnonymisationRecords:
    """Everything a transaction can change."""

    customers: dict[UUID, Known] = field(default_factory=dict)
    events: list[AuditEvent] = field(default_factory=list)
    revoked: list[tuple[UUID, RevokeReason]] = field(default_factory=list)


@dataclass
class AnonymisationStore:
    """The committed state, the dormant keys and the journal of commits."""

    committed: AnonymisationRecords = field(default_factory=AnonymisationRecords)
    dormant: list[UUID] = field(default_factory=list)
    journal: list[str] = field(default_factory=list)

    def add(
        self,
        *,
        key: UUID,
        account: UUID | None = None,
        matters: OpenMatters | None = None,
        last_signed_in_at: datetime | None = None,
        dormant: bool = False,
    ) -> None:
        """Know a customer, with what they have open, and whether the job's page finds them."""
        self.committed.customers[key] = Known(
            subject=ErasureSubject(
                customer_profile_id=key,
                user_account_id=account,
                customer_type=CustomerType.INDIVIDUAL,
                anonymised_at=None,
                last_signed_in_at=last_signed_in_at,
            ),
            matters=matters or OpenMatters(),
        )
        if dormant:
            self.dormant.append(key)

    def known(self, key: UUID) -> Known:
        """Return a committed customer."""
        return self.committed.customers[key]


class _Eraser:
    """The personal data port over the working copy."""

    def __init__(self, store: AnonymisationStore, working: AnonymisationRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def subject_for_update(self, customer_profile_id: UUID) -> ErasureSubject | None:
        """Return the customer as this transaction knows them, or None."""
        known = self._working.customers.get(customer_profile_id)
        return known.subject if known is not None else None

    def open_matters(self, customer_profile_id: UUID) -> OpenMatters:
        """Return what the test said the customer has open."""
        return self._working.customers[customer_profile_id].matters

    def erase(
        self,
        subject: ErasureSubject,
        *,
        profile: AnonymisedProfile,
        account: AnonymisedAccount | None,
        at: datetime,
    ) -> ErasedRows:
        """Keep the values written and stamp the customer as anonymised."""
        known = self._working.customers[subject.customer_profile_id]
        known.subject = replace(known.subject, anonymised_at=at)
        known.profile = profile
        known.account = account
        return ERASED_ROWS

    def dormant_customers(
        self, cutoff: datetime, *, after: UUID | None, limit: int
    ) -> tuple[UUID, ...]:
        """Return the next keys marked dormant and not yet anonymised, in key order."""
        keys = sorted(
            key
            for key in self._store.dormant
            if self._working.customers[key].subject.anonymised_at is None
            and (after is None or key > after)
        )
        return tuple(keys[:limit])


class _Sessions:
    """The part of the session repository an anonymisation revokes through."""

    def __init__(self, working: AnonymisationRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def revoke_all_for_account(
        self, *, user_account_id: UUID, reason: RevokeReason, at: datetime
    ) -> int:
        """Keep that the account's sessions were revoked, and say one was."""
        self._working.revoked.append((user_account_id, reason))
        return 1


class _Audit:
    """The audit log over the working copy."""

    def __init__(self, working: AnonymisationRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def record(self, event: AuditEvent) -> None:
        """Keep the event inside the transaction."""
        self._working.events.append(event)


class _Directory:
    """The read of one customer, as the counter sees one, after the transaction's writes."""

    def __init__(self, working: AnonymisationRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def summary(self, customer_profile_id: UUID) -> CustomerSummary | None:
        """Return the customer with the values this transaction wrote, if any."""
        known = self._working.customers.get(customer_profile_id)
        if known is None:
            return None
        profile = known.profile
        return CustomerSummary(
            id=customer_profile_id,
            display_name=profile.display_name if profile else "Nomsa Dlamini",
            email=known.account.email if known.account else None,
            phone=profile.contact_phone if profile else "082 441 7719",
            has_login=known.subject.user_account_id is not None,
            email_verified=True,
            customer_type=known.subject.customer_type,
            company_name=None,
            id_document_type=IdDocType.SA_ID,
            id_document_last4=profile.id_document_last4 if profile else "4189",
            billing_suburb=profile.billing_suburb if profile else "Salt River",
            billing_city=profile.billing_city if profile else "Cape Town",
            account_status=AccountStatus.ACTIVE,
            trade_discount_percent=Decimal("0.00"),
            no_show_count=0,
            home_branch_code="CBD",
            anonymised_at=known.subject.anonymised_at,
        )


class MemoryAnonymisationUnitOfWork:
    """A unit of work over the anonymisation store."""

    def __init__(self, store: AnonymisationStore) -> None:
        """Bind the unit of work to the store it commits into."""
        self.store = store
        self._working: AnonymisationRecords | None = None

    def __enter__(self) -> Self:
        """Take a working copy of the committed records and build the ports over it."""
        working = copy.deepcopy(self.store.committed)
        self._working = working
        self.personal_data = _Eraser(self.store, working)
        self.sessions = _Sessions(working)
        self.audit = _Audit(working)
        self.customer_directory = _Directory(working)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Throw the working copy away. Anything committed has already been kept."""
        self._working = None

    def commit(self) -> None:
        """Make the working copy the committed state."""
        if self._working is None:
            raise RuntimeError("Attempted to commit an in memory unit of work that is not open.")
        self.store.committed = copy.deepcopy(self._working)
        self.store.journal.append("commit")


__all__ = ["ERASED_ROWS", "AnonymisationStore", "MemoryAnonymisationUnitOfWork"]
