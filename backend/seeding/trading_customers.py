"""The walk in customers of the season, who hire at the counter and have no login.

Thirty made up people from around Cape Town, a third of them trading under a
company name. Each is registered at the branch nearest where they live. Only
the type of identity document and its last four digits are kept, which is all
the schema ever stores, and nobody has a VAT number, so nothing here could be
mistaken for a real registration.

Every phone number is in the 021 555 02xx block, beside the 021 555 01xx
numbers of the branches. The 555 exchange is the made up one the seed already
uses, and the block is also how the loader recognises these customers on a
later run.

Some trade customers carry a trade discount, which an administrator agrees
with a regular account. Each customer joined between January and May 2026,
before the season starts, so their first hire never comes before their
registration. The two customer accounts the seed already creates hire now and
then as well, and are added by the loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from app.domain.enums import CustomerType, IdDocType
from app.domain.walk_in import WalkInCustomer
from seeding.worked_example import SOUTH_AFRICA_STANDARD_TIME

CITY: Final[str] = "Cape Town"
PHONE_BLOCK: Final[str] = "021 555 02"
FIRST_PHONE_NUMBER: Final[int] = 1
NO_DISCOUNT: Final[Decimal] = Decimal("0.00")
# A walk in hires less often than a trade customer who is on site every week.
INDIVIDUAL_WEIGHT: Final[int] = 2
TRADE_WEIGHT: Final[int] = 8
FIRST_REGISTERED_AT: Final[datetime] = datetime(
    2026, 1, 12, 10, 15, tzinfo=SOUTH_AFRICA_STANDARD_TIME
)
DAYS_BETWEEN_REGISTRATIONS: Final[int] = 4

SA_ID: Final[IdDocType] = IdDocType.SA_ID
PASSPORT: Final[IdDocType] = IdDocType.PASSPORT
LICENCE: Final[IdDocType] = IdDocType.DRIVING_LICENCE


@dataclass(frozen=True, slots=True)
class WalkInSeed:
    """One walk in customer as the counter registered them."""

    display_name: str
    company_name: str | None
    street: str
    suburb: str
    postal_code: str
    branch_code: str
    id_document_type: IdDocType
    id_document_last4: str
    trade_discount_percent: Decimal = NO_DISCOUNT


@dataclass(frozen=True, slots=True)
class WalkInProfile:
    """A walk in customer checked by the application's rules, with what the loader adds."""

    key: str
    customer: WalkInCustomer
    branch_code: str
    trade_discount_percent: Decimal
    registered_at: datetime
    weight: int


# I keep each customer to a name line and an address line, so the table reads
# like the counter's register.
# fmt: off
WALK_INS: Final[tuple[WalkInSeed, ...]] = (
    WalkInSeed(
        "Sipho Mthembu", None,
        "31 Lower Main Road", "Observatory", "7925", "CBD", SA_ID, "2207",
    ),
    WalkInSeed(
        "Annelie van der Merwe", None,
        "8 Wellington Road", "Durbanville", "7550", "BLV", SA_ID, "6158",
    ),
    WalkInSeed(
        "Ridwaan Davids", None,
        "54 Klipfontein Road", "Athlone", "7764", "CBD", SA_ID, "3091",
    ),
    WalkInSeed(
        "Lindiwe Khumalo", None,
        "17 Voortrekker Road", "Bellville", "7530", "BLV", LICENCE, "7714",
    ),
    WalkInSeed(
        "Pieter Botha", None,
        "6 Lourensford Road", "Somerset West", "7130", "SMW", SA_ID, "5082",
    ),
    WalkInSeed(
        "Fatima Isaacs", None,
        "22 Belmont Road", "Rondebosch", "7700", "CBD", SA_ID, "4426",
    ),
    WalkInSeed(
        "Themba Ngubane", None,
        "41 Van Riebeeck Road", "Kuils River", "7580", "BLV", SA_ID, "0937",
    ),
    WalkInSeed(
        "Charlene Jacobs", None,
        "15 Beach Road", "Strand", "7140", "SMW", LICENCE, "8340",
    ),
    WalkInSeed(
        "Johan Steyn", None,
        "3 Sir Lowry's Pass Road", "Gordon's Bay", "7150", "SMW", SA_ID, "1265",
    ),
    WalkInSeed(
        "Nosipho Zulu", None,
        "70 Victoria Road", "Woodstock", "7925", "CBD", SA_ID, "6603",
    ),
    WalkInSeed(
        "Graham Fortuin", None,
        "12 AZ Berman Drive", "Mitchells Plain", "7785", "CBD", SA_ID, "9150",
    ),
    WalkInSeed(
        "Ayesha Patel", None,
        "9 Old Paarl Road", "Brackenfell", "7560", "BLV", PASSPORT, "4471",
    ),
    WalkInSeed(
        "Kagiso Molefe", None,
        "26 Main Road", "Claremont", "7708", "CBD", SA_ID, "3318",
    ),
    WalkInSeed(
        "Marelize Coetzee", None,
        "11 Dorp Street", "Stellenbosch", "7600", "SMW", SA_ID, "7029",
    ),
    WalkInSeed(
        "Lwazi Dube", None,
        "38 Tygerberg Valley Road", "Parow", "7500", "BLV", LICENCE, "2846",
    ),
    WalkInSeed(
        "Bronwyn Hendricks", None,
        "5 Victoria Road", "Plumstead", "7800", "CBD", SA_ID, "5531",
    ),
    WalkInSeed(
        "Riaan du Plessis", None,
        "19 Old Paarl Road", "Kraaifontein", "7570", "BLV", SA_ID, "0482",
    ),
    WalkInSeed(
        "Zanele Mahlangu", None,
        "27 Andries Pretorius Street", "Somerset West", "7130", "SMW", PASSPORT, "6697",
    ),
    WalkInSeed(
        "Yusuf Salie", None,
        "4 Wale Street", "Bo-Kaap", "8001", "CBD", SA_ID, "1873",
    ),
    WalkInSeed(
        "Elsabe Venter", None,
        "13 Voortrekker Road", "Goodwood", "7460", "BLV", SA_ID, "8205",
    ),
    WalkInSeed(
        "Andile Sithole", "Sithole Plumbing and Drainage",
        "48 Albert Road", "Salt River", "7925", "CBD", SA_ID, "3964", Decimal("5.00"),
    ),
    WalkInSeed(
        "Craig Petersen", "Petersen Paving",
        "21 Modderdam Road", "Bellville South", "7530", "BLV", SA_ID, "7148", Decimal("10.00"),
    ),
    WalkInSeed(
        "Mandla Nkosi", "Nkosi Civils",
        "62 Lansdowne Road", "Khayelitsha", "7784", "CBD", SA_ID, "2590",
    ),
    WalkInSeed(
        "Hennie Kruger", "Kruger Bouwerke",
        "7 Main Road", "Strand", "7140", "SMW", SA_ID, "6311", Decimal("7.50"),
    ),
    WalkInSeed(
        "Shireen Abrahams", "Cape Shopfitters",
        "15 Bofors Circle", "Epping", "7460", "CBD", LICENCE, "4057", Decimal("5.00"),
    ),
    WalkInSeed(
        "Bongani Mokoena", "Mokoena Electrical",
        "33 Voortrekker Road", "Parow", "7500", "BLV", SA_ID, "9726",
    ),
    WalkInSeed(
        "Werner Smit", "Helderberg Landscapes",
        "10 Bright Street", "Somerset West", "7130", "SMW", SA_ID, "0819", Decimal("10.00"),
    ),
    WalkInSeed(
        "Nadia Adams", "Adams Tiling and Floors",
        "29 Main Road", "Wynberg", "7800", "CBD", SA_ID, "5372", Decimal("5.00"),
    ),
    WalkInSeed(
        "Tebogo Masilela", "Masilela Construction",
        "16 Vissershok Road", "Durbanville", "7550", "BLV", PASSPORT, "2683", Decimal("7.50"),
    ),
    WalkInSeed(
        "Gareth Williams", "Williams Roofing",
        "2 Faure Street", "Gordon's Bay", "7150", "SMW", SA_ID, "8451",
    ),
)
# fmt: on


def walk_in_profiles() -> tuple[WalkInProfile, ...]:
    """Return every walk in customer, checked by the rules the counter's form is checked by.

    Raises:
        ValidationFailure: If a record breaks a rule the application enforces on
            a walk in, which would be a mistake in the table above.

    """
    return tuple(_profile_of(position, seed) for position, seed in enumerate(WALK_INS))


def phone_of(position: int) -> str:
    """Return the made up phone number of the walk in at a position, for example 021 555 0201."""
    return f"{PHONE_BLOCK}{position + FIRST_PHONE_NUMBER:02d}"


def _profile_of(position: int, seed: WalkInSeed) -> WalkInProfile:
    """Return one walk in, checked, with its key, its discount and when it registered."""
    trade = seed.company_name is not None
    customer = WalkInCustomer.registering(
        display_name=seed.display_name,
        phone=phone_of(position),
        id_document_type=seed.id_document_type,
        id_document_last4=seed.id_document_last4,
        billing_address_line1=seed.street,
        billing_suburb=seed.suburb,
        billing_city=CITY,
        billing_postal_code=seed.postal_code,
        customer_type=CustomerType.TRADE if trade else CustomerType.INDIVIDUAL,
        company_name=seed.company_name,
        vat_number=None,
    )
    return WalkInProfile(
        key=phone_of(position),
        customer=customer,
        branch_code=seed.branch_code,
        trade_discount_percent=seed.trade_discount_percent,
        registered_at=FIRST_REGISTERED_AT
        + timedelta(days=DAYS_BETWEEN_REGISTRATIONS * position),
        weight=TRADE_WEIGHT if trade else INDIVIDUAL_WEIGHT,
    )
