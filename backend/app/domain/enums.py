"""Domain enumerations.

Each of these becomes a native PostgreSQL enum type. The type names are the
module level constants at the foot of the file, so the migration and the models
import one symbol per type and cannot disagree about what a column is declared
as. The names are deliberately not class attributes, because a plain assignment
inside an Enum body becomes an enum member.

Only the members the walking skeleton needs are declared. Members that exist in
the canonical model but are not exercised yet are still listed where leaving
them out would make a legitimate stored value unrepresentable.
"""

from __future__ import annotations

from enum import Enum


class DomainEnum(str, Enum):
    """Base for enumerations that are stored as native PostgreSQL enum types."""

    @classmethod
    def values(cls) -> list[str]:
        """Return the member values in declaration order, for DDL generation."""
        return [member.value for member in cls]

    def __str__(self) -> str:
        """Return the stored value rather than the `Class.MEMBER` repr."""
        # str() rather than a bare return. Enum.value is typed Any in the
        # standard library stubs, and returning it unwrapped hands an Any back
        # to every caller of str() on a domain enum.
        return str(self.value)


class UserRole(DomainEnum):
    """The single role carried by a UserAccount. A role is never a set."""

    CUSTOMER = "CUSTOMER"
    COUNTER_STAFF = "COUNTER_STAFF"
    ADMIN = "ADMIN"


class AssetStatus(DomainEnum):
    """Asset lifecycle status. There is deliberately no RESERVED member.

    Future occupancy is derived from AssetAllocation rows. A RESERVED status
    would be a second source of truth able to disagree with the exclusion
    constraint.
    """

    INTAKE = "INTAKE"
    AVAILABLE = "AVAILABLE"
    ON_HIRE = "ON_HIRE"
    QUARANTINED = "QUARANTINED"
    UNDER_REPAIR = "UNDER_REPAIR"
    LOST = "LOST"
    RETIRED = "RETIRED"


class ConditionGrade(DomainEnum):
    """Condition grade recorded at checkout and return. A is best."""

    A = "A"
    B = "B"
    C = "C"


class ReservationStatus(DomainEnum):
    """Reservation lifecycle status, governed by the State pattern in the domain."""

    DRAFT = "DRAFT"
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    COLLECTED = "COLLECTED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    EXPIRED = "EXPIRED"


class AllocationStatus(DomainEnum):
    """Whether an allocation still occupies its asset, and if not, why not.

    ACTIVE is the only status the exclusion constraint considers, because the
    constraint is filtered on `released_at IS NULL` and the release state check
    ties `released_at` to this column.
    """

    ACTIVE = "ACTIVE"
    RETURNED = "RETURNED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    EXPIRED = "EXPIRED"
    REALLOCATED = "REALLOCATED"

    @classmethod
    def released_values(cls) -> list[str]:
        """Return every status that requires a `released_at` timestamp."""
        return [member.value for member in cls if member is not cls.ACTIVE]


USER_ROLE_TYPE = "user_role"
ASSET_STATUS_TYPE = "asset_status"
CONDITION_GRADE_TYPE = "condition_grade"
RESERVATION_STATUS_TYPE = "reservation_status"
ALLOCATION_STATUS_TYPE = "allocation_status"
