"""The SQL customer repository of the identity module, on the session of its unit of work.

It counts a late cancellation (BR-16) and a booking that was not collected
(BR-17), each in one statement so two at once are both counted, and writes
the standing of a customer (BR-18). It writes the profile of somebody who has
just registered or of a walk-in, and reads and writes a customer's own
details, which span the profile and the account and are read in one
statement. The branch repository, the branch directory and the customer
directory are modules of their own.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, update
from sqlmodel import Session, col, select

from app.domain import identity as domain
from app.domain.business_time import in_business_time
from app.domain.customer_account import CustomerDetails, NewCustomer
from app.domain.enums import AccountStatus
from app.domain.walk_in import WalkInCustomer
from app.infrastructure.booking_mapping import required_utc
from app.infrastructure.models import Branch, CustomerProfile, UserAccount

logger = logging.getLogger(__name__)

COUNT_INCREMENT: Final[int] = 1


class SqlCustomerRepository:
    """Reads customer profiles, and counts on them, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def profile_for_account(self, user_account_id: UUID) -> domain.CustomerProfile | None:
        """Return the customer profile that belongs to a sign in account."""
        return self._find(
            col(CustomerProfile.user_account_id) == user_account_id,
            {"customer_user_id": str(user_account_id)},
        )

    def get(self, customer_profile_id: UUID) -> domain.CustomerProfile | None:
        """Return the customer profile with this key, or None when there is none."""
        return self._find(
            col(CustomerProfile.id) == customer_profile_id,
            {"customer_profile_id": str(customer_profile_id)},
        )

    def record_late_cancellation(self, customer_profile_id: UUID) -> None:
        """Count one late cancellation on a customer profile (BR-16).

        The count is raised by the database, in one statement, so two
        cancellations at the same moment are both counted.
        """
        self._session.execute(
            update(CustomerProfile)
            .where(col(CustomerProfile.id) == customer_profile_id)
            .values(
                late_cancellation_count=col(CustomerProfile.late_cancellation_count)
                + COUNT_INCREMENT
            )
        )
        logger.info(
            "identity.late_cancellation_recorded",
            extra={"customer_profile_id": str(customer_profile_id)},
        )

    def get_for_update(self, customer_profile_id: UUID) -> domain.CustomerProfile | None:
        """Return the customer profile with this key, locked until the transaction ends."""
        return self._find(
            col(CustomerProfile.id) == customer_profile_id,
            {"customer_profile_id": str(customer_profile_id)},
            for_update=True,
        )

    def record_no_show(self, customer_profile_id: UUID) -> None:
        """Raise the running count of bookings a customer did not collect by one (BR-17)."""
        self._session.execute(
            update(CustomerProfile)
            .where(col(CustomerProfile.id) == customer_profile_id)
            .values(no_show_count=col(CustomerProfile.no_show_count) + COUNT_INCREMENT)
        )
        logger.info(
            "identity.no_show_recorded", extra={"customer_profile_id": str(customer_profile_id)}
        )

    def save_account_status(self, customer_profile_id: UUID, status: AccountStatus) -> None:
        """Write the standing of a customer (BR-18)."""
        self._session.execute(
            update(CustomerProfile)
            .where(col(CustomerProfile.id) == customer_profile_id)
            .values(account_status=status)
        )
        logger.info(
            "identity.account_status_saved",
            extra={"customer_profile_id": str(customer_profile_id), "status": status.value},
        )

    def add_registered(
        self, *, user_account_id: UUID, registered_branch_id: UUID, customer: NewCustomer
    ) -> UUID:
        """Write the profile of somebody who has just registered and return its key."""
        profile_id = uuid4()
        self._session.add(
            CustomerProfile(
                id=profile_id,
                user_account_id=user_account_id,
                customer_type=customer.customer_type,
                display_name=customer.full_name,
                id_document_type=customer.id_document_type,
                id_document_last4=customer.id_document_last4,
                contact_phone=customer.phone,
                billing_address_line1=customer.billing_address_line1,
                billing_suburb=customer.billing_suburb,
                billing_city=customer.billing_city,
                billing_postal_code=customer.billing_postal_code,
                account_status=customer.account_status,
                trade_discount_percent=customer.trade_discount_percent,
                registered_branch_id=registered_branch_id,
            )
        )
        self._session.flush()
        added = {"customer_profile_id": str(profile_id), "customer_user_id": str(user_account_id)}
        logger.info("identity.customer_profile_added", extra=added)
        return profile_id

    def add_walk_in(self, *, registered_branch_id: UUID, customer: WalkInCustomer) -> UUID:
        """Write the profile of a walk-in, which has no account, and return its key."""
        profile_id = uuid4()
        details = customer.details
        self._session.add(
            CustomerProfile(
                id=profile_id,
                user_account_id=None,
                customer_type=customer.customer_type,
                display_name=details.full_name,
                company_name=customer.company_name,
                vat_number=customer.vat_number,
                id_document_type=details.id_document_type,
                id_document_last4=details.id_document_last4,
                contact_phone=details.phone,
                billing_address_line1=details.billing_address_line1,
                billing_suburb=details.billing_suburb,
                billing_city=details.billing_city,
                billing_postal_code=details.billing_postal_code,
                account_status=details.account_status,
                trade_discount_percent=details.trade_discount_percent,
                registered_branch_id=registered_branch_id,
            )
        )
        self._session.flush()
        logger.info(
            "identity.walk_in_profile_added",
            extra={"customer_profile_id": str(profile_id), "branch_id": str(registered_branch_id)},
        )
        return profile_id

    def details_for_account(
        self, user_account_id: UUID, *, for_update: bool = False
    ) -> CustomerDetails | None:
        """Return a customer's own details, or None when the account has no profile.

        The profile, the account and the code of the home branch are read in
        one statement. An edit locks the profile and the account, and not the
        branch, which every booking at that branch reads.
        """
        statement = (
            select(CustomerProfile, UserAccount, col(Branch.code))
            .join(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
            .join(Branch, col(Branch.id) == col(CustomerProfile.registered_branch_id))
            .where(col(CustomerProfile.user_account_id) == user_account_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update(
                of=[col(CustomerProfile.id), col(UserAccount.id)]
            )
        found = self._session.exec(statement).first()
        logger.debug(
            "identity.customer_details_lookup_finished",
            extra={
                "customer_user_id": str(user_account_id),
                "found": found is not None,
                "locked": for_update,
            },
        )
        if found is None:
            return None
        profile, account, branch_code = found
        return _details_of(profile, account, branch_code)

    def save_details(self, details: CustomerDetails) -> None:
        """Write the contact and billing fields of a customer, on both rows.

        Raises:
            RuntimeError: If either row is missing, which would mean a use
                case is saving details it never loaded.

        """
        profile = self._session.get(CustomerProfile, details.profile_id)
        account = self._session.get(UserAccount, details.user_account_id)
        if profile is None or account is None:
            raise RuntimeError(
                f"Attempted to save the details of customer profile {details.profile_id}, "
                "which has no row. Load the details through this repository before saving them."
            )
        account.full_name = details.full_name
        account.phone = details.phone
        profile.display_name = details.full_name
        profile.contact_phone = details.phone
        profile.company_name = details.company_name
        profile.vat_number = details.vat_number
        profile.billing_address_line1 = details.billing_address_line1
        profile.billing_suburb = details.billing_suburb
        profile.billing_city = details.billing_city
        profile.billing_postal_code = details.billing_postal_code
        self._session.add_all([profile, account])
        self._session.flush()
        logger.info(
            "identity.customer_details_saved",
            extra={"customer_profile_id": str(details.profile_id)},
        )

    def _find(
        self, condition: ColumnElement[bool], sought: dict[str, str], *, for_update: bool = False
    ) -> domain.CustomerProfile | None:
        """Return the one profile a condition picks, with what its account says.

        The address of the account and the moment it was verified are read in
        the same statement, because a confirmation is sent to the first and
        allowed by the second (BR-47). The join is an outer one, because a
        walk-in has a profile and no account. A lock takes the profile alone,
        and the profile is read again under it.
        """
        statement = (
            select(CustomerProfile, col(UserAccount.email), col(UserAccount.email_verified_at))
            .outerjoin(UserAccount, col(UserAccount.id) == col(CustomerProfile.user_account_id))
            .where(condition)
        )
        if for_update:
            statement = statement.with_for_update(of=CustomerProfile).execution_options(
                populate_existing=True
            )
        found = self._session.exec(statement).first()
        logger.debug(
            "identity.customer_profile_lookup_finished",
            extra={**sought, "found": found is not None, "locked": for_update},
        )
        if found is None:
            return None
        row, email, email_verified_at = found
        return domain.CustomerProfile(
            id=row.id,
            user_account_id=row.user_account_id,
            display_name=row.display_name,
            account_status=row.account_status,
            email=email,
            trade_discount_percent=Decimal(row.trade_discount_percent),
            email_verified=email_verified_at is not None,
        )


def _details_of(
    profile: CustomerProfile, account: UserAccount, branch_code: str
) -> CustomerDetails:
    """Return a customer's own details from the profile row and the account row."""
    opened_at = required_utc(profile.created_at, "customer_profile.created_at")
    return CustomerDetails(
        profile_id=profile.id,
        user_account_id=account.id,
        full_name=account.full_name,
        email=account.email,
        email_verified=account.email_verified_at is not None,
        phone=profile.contact_phone,
        customer_type=profile.customer_type,
        company_name=profile.company_name,
        vat_number=profile.vat_number,
        id_document_type=profile.id_document_type,
        id_document_last4=profile.id_document_last4,
        billing_address_line1=profile.billing_address_line1,
        billing_suburb=profile.billing_suburb,
        billing_city=profile.billing_city,
        billing_postal_code=profile.billing_postal_code,
        account_status=profile.account_status,
        trade_discount_percent=Decimal(profile.trade_discount_percent),
        no_show_count=profile.no_show_count,
        home_branch_code=branch_code,
        member_since=in_business_time(opened_at).date(),
    )
