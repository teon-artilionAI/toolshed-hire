"""The accounts and the customer profiles the seed creates.

One administrator, a counter assistant at each of two branches, and two
customers, one trading and one private. The names match the prototype where it
already had them. The addresses, the phone numbers, the company and the VAT
number are made up. The private customer's mailbox is on a reserved example
domain, so a message sent to it by a later feature reaches nobody.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.domain.enums import CustomerType, IdDocType, UserRole

CITY: Final[str] = "Cape Town"

ADMIN_EMAIL: Final[str] = "marius@toolshedhire.co.za"
CBD_COUNTER_EMAIL: Final[str] = "elmarie@toolshedhire.co.za"
BLV_COUNTER_EMAIL: Final[str] = "thabo@toolshedhire.co.za"
TRADE_CUSTOMER_EMAIL: Final[str] = "w.adonis@buildright.co.za"
INDIVIDUAL_CUSTOMER_EMAIL: Final[str] = "nomsa.dlamini@example.com"


@dataclass(frozen=True, slots=True)
class AccountSeed:
    """One sign in account. I use the email address as the natural key.

    The branch code is set for counter staff and for nobody else, which is the
    rule the account table checks.
    """

    email: str
    full_name: str
    role: UserRole
    branch_code: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class CustomerProfileSeed:
    """The hire profile of one customer account, matched through its email address."""

    email: str
    customer_type: CustomerType
    display_name: str
    company_name: str | None
    vat_number: str | None
    id_document_type: IdDocType
    id_document_last4: str
    contact_phone: str
    billing_address_line1: str
    billing_suburb: str
    billing_city: str
    billing_postal_code: str
    registered_branch_code: str


ACCOUNTS: Final[tuple[AccountSeed, ...]] = (
    AccountSeed(
        email=ADMIN_EMAIL,
        full_name="Marius Pretorius",
        role=UserRole.ADMIN,
        branch_code=None,
        phone=None,
    ),
    AccountSeed(
        email=CBD_COUNTER_EMAIL,
        full_name="Elmarie Fourie",
        role=UserRole.COUNTER_STAFF,
        branch_code="CBD",
        phone=None,
    ),
    AccountSeed(
        email=BLV_COUNTER_EMAIL,
        full_name="Thabo Ncube",
        role=UserRole.COUNTER_STAFF,
        branch_code="BLV",
        phone=None,
    ),
    AccountSeed(
        email=TRADE_CUSTOMER_EMAIL,
        full_name="Wesley Adonis",
        role=UserRole.CUSTOMER,
        branch_code=None,
        phone="082 441 7719",
    ),
    AccountSeed(
        email=INDIVIDUAL_CUSTOMER_EMAIL,
        full_name="Nomsa Dlamini",
        role=UserRole.CUSTOMER,
        branch_code=None,
        phone="073 228 5104",
    ),
)

CUSTOMER_PROFILES: Final[tuple[CustomerProfileSeed, ...]] = (
    CustomerProfileSeed(
        email=TRADE_CUSTOMER_EMAIL,
        customer_type=CustomerType.TRADE,
        display_name="Wesley Adonis",
        company_name="BuildRight Construction",
        vat_number="4720318865",
        id_document_type=IdDocType.SA_ID,
        id_document_last4="4189",
        contact_phone="082 441 7719",
        billing_address_line1="27 Durham Avenue",
        billing_suburb="Salt River",
        billing_city=CITY,
        billing_postal_code="7925",
        registered_branch_code="CBD",
    ),
    CustomerProfileSeed(
        email=INDIVIDUAL_CUSTOMER_EMAIL,
        customer_type=CustomerType.INDIVIDUAL,
        display_name="Nomsa Dlamini",
        company_name=None,
        vat_number=None,
        id_document_type=IdDocType.SA_ID,
        id_document_last4="0086",
        contact_phone="073 228 5104",
        billing_address_line1="14 Tallent Street",
        billing_suburb="Parow",
        billing_city=CITY,
        billing_postal_code="7500",
        registered_branch_code="BLV",
    ),
)
