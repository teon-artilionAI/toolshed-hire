"""The in memory repository of a customer's own details.

`AccountCustomers` is the customer repository the identity unit of work hands
out. It does what the booking one does and adds the three things registration
and the profile need, which are writing the profile of a new customer, reading
a customer's details and saving an edit.

The details live in the working copy of the identity records, so they are only
kept when the unit of work commits. An edit writes the name and the phone
number through to the account as well, as the SQL repository does, so a test
can read both copies.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import TYPE_CHECKING, Final
from uuid import UUID, uuid4

from app.domain.customer_account import CustomerDetails, NewCustomer
from tests.support.memory_reference import MemoryCustomers

if TYPE_CHECKING:
    from tests.support.memory import MemoryStore, Records
    from tests.support.memory_identity import IdentityRecords

# The business day of the fixed clock, which is when an in memory profile opens.
MEMBER_SINCE: Final[date] = date(2026, 3, 2)
NO_SHOWS_AT_REGISTRATION: Final[int] = 0


class AccountCustomers(MemoryCustomers):
    """The customer repository, with a customer's own details as well."""

    def __init__(self, store: MemoryStore, working: Records, identity: IdentityRecords) -> None:
        """Bind to the store and to the two working copies of one transaction."""
        super().__init__(store, working)
        self._identity = identity

    def add_registered(
        self, *, user_account_id: UUID, registered_branch_id: UUID, customer: NewCustomer
    ) -> UUID:
        """Keep the details of somebody who has just registered and return the profile key."""
        account = self._identity.accounts[user_account_id]
        profile_id = uuid4()
        self._identity.details[user_account_id] = CustomerDetails(
            profile_id=profile_id,
            user_account_id=user_account_id,
            full_name=customer.full_name,
            email=account.email,
            email_verified=account.email_verified,
            phone=customer.phone,
            customer_type=customer.customer_type,
            company_name=None,
            vat_number=None,
            id_document_type=customer.id_document_type,
            id_document_last4=customer.id_document_last4,
            billing_address_line1=customer.billing_address_line1,
            billing_suburb=customer.billing_suburb,
            billing_city=customer.billing_city,
            billing_postal_code=customer.billing_postal_code,
            account_status=customer.account_status,
            trade_discount_percent=customer.trade_discount_percent,
            no_show_count=NO_SHOWS_AT_REGISTRATION,
            home_branch_code=self._store.branches[registered_branch_id].code,
            member_since=MEMBER_SINCE,
        )
        return profile_id

    def details_for_account(
        self, user_account_id: UUID, *, for_update: bool = False
    ) -> CustomerDetails | None:
        """Return a copy of a customer's details, if the account has a profile."""
        return copy.deepcopy(self._identity.details.get(user_account_id))

    def save_details(self, details: CustomerDetails) -> None:
        """Keep an edit, on the details and on the account behind them."""
        self._identity.details[details.user_account_id] = copy.deepcopy(details)
        account = self._identity.accounts.get(details.user_account_id)
        if account is not None:
            account.full_name = details.full_name
            account.phone = details.phone


__all__ = ["MEMBER_SINCE", "AccountCustomers"]
