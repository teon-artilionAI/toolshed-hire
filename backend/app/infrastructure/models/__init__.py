"""SQLModel table classes, one module per subject area.

All seventeen tables of the documented schema are modelled. The modules follow
the subject areas of the entity relationship diagrams. `identity` holds the
branch, the account, the customer profile and the refresh session. `catalogue`
holds the category, the product model and the asset. `booking` holds the
reservation, its lines and the allocations. `hire` holds the rental, its items,
the damage reports and the charges. `evidence` holds the audit log, the
notifications and the rate limit counters.

Every class is re-exported here, so `from app.infrastructure.models import
Asset` works whichever module the class lives in.

Two things are worth knowing before reading any of them.

The classes declare columns and keys, which is what the mapper needs. The check
constraints, the exclusion constraint and the indexes are created by the
migration and are not repeated on the classes, so there is one authoritative
listing of them and not two that could drift.

Enum columns bind to native PostgreSQL enum types with `create_type=False`.
The types are created by the migration, which is also the only place tables are
created. `SQLModel.metadata.create_all` is never used against a real database.
"""

from __future__ import annotations

from app.infrastructure.models.booking import AssetAllocation, Reservation, ReservationLine
from app.infrastructure.models.catalogue import Asset, Category, ProductModel
from app.infrastructure.models.evidence import AuditEvent, Notification, RateLimitCounter
from app.infrastructure.models.hire import Charge, DamageReport, Rental, RentalItem
from app.infrastructure.models.identity import (
    Branch,
    CustomerProfile,
    RefreshSession,
    UserAccount,
)

__all__ = [
    "Asset",
    "AssetAllocation",
    "AuditEvent",
    "Branch",
    "Category",
    "Charge",
    "CustomerProfile",
    "DamageReport",
    "Notification",
    "ProductModel",
    "RateLimitCounter",
    "RefreshSession",
    "Rental",
    "RentalItem",
    "Reservation",
    "ReservationLine",
    "UserAccount",
]
