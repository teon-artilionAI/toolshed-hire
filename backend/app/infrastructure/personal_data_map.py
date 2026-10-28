"""Which tables hold a customer's personal information, and where in them it is.

POPIA gives a customer the right to see everything held about them and to have
it removed once it is no longer needed. Both depend on knowing, table by table,
what is held. This map is that knowledge in one place. The export of a
customer's data reads every table it marks as customer data, the anonymising
routine clears the columns it names, and the register of processing lists the
same categories.

Every table in the schema is in the map, and a test fails when one is not, so a
table added later has to be classified in the pull request that adds it. The
same test follows the foreign keys. A table that reaches a customer profile or
a user account through them is customer data, unless it is marked as linked to
staff accounts only, with the reason.

The map names columns, not values. Free text columns are listed apart from the
identifying ones, because a note can hold a name or a number someone typed into
it, and an anonymising routine has to clear it even though its column name says
nothing about a person.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

# How a table reaches the customer when it is the customer's own record.
ITSELF: Final[str] = "itself"


@dataclass(frozen=True, slots=True)
class CustomerData:
    """A table that holds information about a customer.

    Attributes:
        reached_through: The foreign key column that leads, directly or through
            other tables, to the customer profile or the user account, or
            ITSELF for those two tables.
        identifying_columns: Columns that name, reach or describe a person.
        free_text_columns: Columns someone types into, which can hold personal
            information although their name does not say so.
        subject_entity_types: For a polymorphic table such as `audit_event`,
            the entity types whose rows describe this customer. The exporter
            uses this explicit list rather than guessing a polymorphic key.

    """

    reached_through: str
    identifying_columns: tuple[str, ...] = ()
    free_text_columns: tuple[str, ...] = ()
    subject_entity_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NoCustomerData:
    """A table that holds nothing about a customer.

    Attributes:
        reason: Why, in one line.
        staff_link_only: True when the table's foreign keys reach a user
            account, but only ever a staff account, so the link is not to a
            customer.

    """

    reason: str
    staff_link_only: bool = field(default=False)


type TableClassification = CustomerData | NoCustomerData

_MAP: dict[str, TableClassification] = {
    # The customer's own records.
    "customer_profile": CustomerData(
        reached_through=ITSELF,
        identifying_columns=(
            "display_name",
            "company_name",
            "vat_number",
            "id_document_last4",
            "contact_phone",
            "billing_address_line1",
            "billing_suburb",
            "billing_city",
            "billing_postal_code",
        ),
    ),
    "user_account": CustomerData(
        reached_through=ITSELF,
        identifying_columns=("email", "full_name", "phone"),
    ),
    "refresh_session": CustomerData(
        reached_through="user_account_id",
        identifying_columns=("user_agent", "ip_address"),
    ),
    # Bookings and hires, which are the customer's through the reservation.
    "reservation": CustomerData(
        reached_through="customer_profile_id",
        free_text_columns=("notes", "cancellation_reason"),
    ),
    "reservation_line": CustomerData(reached_through="reservation_id"),
    "asset_allocation": CustomerData(reached_through="reservation_line_id"),
    "rental": CustomerData(reached_through="reservation_id"),
    "rental_item": CustomerData(reached_through="rental_id", free_text_columns=("notes",)),
    "damage_report": CustomerData(
        reached_through="rental_item_id",
        free_text_columns=("description", "resolution_notes"),
    ),
    # The object key reaches the photograph itself, which can show the customer
    # or what they hired, so it is listed with the columns that identify. Erasing
    # a customer's data means removing the object it names from the bucket.
    "damage_photo": CustomerData(
        reached_through="damage_report_id",
        identifying_columns=("object_key",),
    ),
    "charge": CustomerData(
        reached_through="rental_id",
        free_text_columns=("description", "waiver_reason", "payment_reference"),
    ),
    "notification": CustomerData(
        reached_through="reservation_id",
        identifying_columns=("recipient_email",),
        free_text_columns=("subject", "last_error"),
    ),
    # The audit trail records who did what, customers included, and what changed.
    "audit_event": CustomerData(
        reached_through="actor_user_id",
        identifying_columns=("ip_address",),
        free_text_columns=("before_state", "after_state"),
        subject_entity_types=(
            "user_account",
            "customer_profile",
            "reservation",
            "rental",
            "charge",
            "damage_report",
            "notification",
            "asset",
        ),
    ),
    # Nothing about a customer.
    "rate_limit_counter": NoCustomerData(
        "Keyed by a one way hash of the throttled key, and swept once its window has passed."
    ),
    "branch": NoCustomerData("The business's own branches."),
    "branch_trading_hours": NoCustomerData("When each branch is open."),
    "closure_day": NoCustomerData(
        "Days a branch is closed. Its accounts are the staff who set or cancelled them.",
        staff_link_only=True,
    ),
    "category": NoCustomerData("The catalogue's categories."),
    "product_model": NoCustomerData("The catalogue's models and their prices."),
    "asset": NoCustomerData("The fleet's units."),
}

PERSONAL_DATA_MAP: Final[Mapping[str, TableClassification]] = MappingProxyType(_MAP)


def customer_data_tables() -> tuple[str, ...]:
    """Return the tables that hold customer data, in the order of the map."""
    return tuple(name for name, kind in PERSONAL_DATA_MAP.items() if isinstance(kind, CustomerData))
