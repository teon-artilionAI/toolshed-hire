"""Domain enumerations.

Each of these becomes a native PostgreSQL enum type, and there are seventeen of
them, which is every role, status and reason the data schema section of the
design document names. The type names are the module level constants at the
foot of the file, so the models import one symbol per type and cannot disagree
about what a column is declared as. The names are deliberately not class
attributes, because a plain assignment inside an Enum body becomes an enum
member.

Adding a member here is not enough to store it. The database type has to gain
the value through a migration first, and an integration test compares the two
so that the omission fails loudly rather than at the first insert.
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


class CustomerType(DomainEnum):
    """Whether a customer hires as a member of the public or as a trade account."""

    INDIVIDUAL = "INDIVIDUAL"
    TRADE = "TRADE"


class IdDocType(DomainEnum):
    """The identity document a customer presented. Only its last four digits are kept."""

    SA_ID = "SA_ID"
    PASSPORT = "PASSPORT"
    DRIVING_LICENCE = "DRIVING_LICENCE"


class AccountStatus(DomainEnum):
    """Customer account standing. ON_HOLD is set by the no-show rule (BR-18)."""

    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    BLACKLISTED = "BLACKLISTED"


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
    RETURNED = "RETURNED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    EXPIRED = "EXPIRED"


class ReleaseReason(DomainEnum):
    """Why an allocation stopped occupying its asset.

    There is no ACTIVE member. An allocation is active exactly while
    `released_at` is null, which is the predicate the exclusion constraint is
    filtered on, and a release state check makes the reason and the timestamp
    arrive together. A status column beside them would be a second statement of
    the same fact.
    """

    RETURNED = "RETURNED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    EXPIRED = "EXPIRED"
    REALLOCATED = "REALLOCATED"


class RentalStatus(DomainEnum):
    """Rental lifecycle status, governed by BR-29, BR-52 and BR-53."""

    OPEN = "OPEN"
    OVERDUE = "OVERDUE"
    PARTIALLY_RETURNED = "PARTIALLY_RETURNED"
    RETURNED = "RETURNED"
    SETTLED = "SETTLED"


class ChargeType(DomainEnum):
    """What a money line on a rental is for. Deposit movements are charges too."""

    HIRE = "HIRE"
    DEPOSIT_HOLD = "DEPOSIT_HOLD"
    DEPOSIT_RELEASE = "DEPOSIT_RELEASE"
    DEPOSIT_FORFEIT = "DEPOSIT_FORFEIT"
    LATE_FEE = "LATE_FEE"
    DAMAGE_RECOVERY = "DAMAGE_RECOVERY"
    CLEANING = "CLEANING"
    ADJUSTMENT = "ADJUSTMENT"


class ChargeStatus(DomainEnum):
    """Where a charge stands. A settled charge is never edited (BR-24)."""

    PENDING = "PENDING"
    SETTLED = "SETTLED"
    WAIVED = "WAIVED"
    REVERSED = "REVERSED"


class DamageSeverity(DomainEnum):
    """How bad the damage is, as the counter judged it when the report was filed.

    A WRITE_OFF severity does not retire the unit by itself. Only a report the
    owner resolves as WRITTEN_OFF does that (BR-38), so the decision to retire
    a unit is always the owner's.
    """

    MINOR = "MINOR"
    MAJOR = "MAJOR"
    WRITE_OFF = "WRITE_OFF"


class DamageStatus(DomainEnum):
    """Where a damage report stands between being raised and being closed."""

    OPEN = "OPEN"
    UNDER_REPAIR = "UNDER_REPAIR"
    RESOLVED = "RESOLVED"
    WRITTEN_OFF = "WRITTEN_OFF"


class NotificationType(DomainEnum):
    """What an outbound message is about. Phase one sends one kind only."""

    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"


class NotificationChannel(DomainEnum):
    """How an outbound message travels. Phase one sends email only."""

    EMAIL = "EMAIL"


class NotificationStatus(DomainEnum):
    """Delivery outcome of a notification. A FAILED row can be sent again."""

    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"


class RevokeReason(DomainEnum):
    """Why a refresh session stopped being usable (BR-48)."""

    LOGOUT = "LOGOUT"
    ROTATION = "ROTATION"
    REUSE_DETECTED = "REUSE_DETECTED"
    ADMIN_REVOKE = "ADMIN_REVOKE"


# One constant per PostgreSQL type, named after the type with a _TYPE suffix.
# Four of the types already end in the word type, which is why those constants
# say it twice.
USER_ROLE_TYPE = "user_role"
CUSTOMER_TYPE_TYPE = "customer_type"
ID_DOC_TYPE_TYPE = "id_doc_type"
ACCOUNT_STATUS_TYPE = "account_status"
ASSET_STATUS_TYPE = "asset_status"
CONDITION_GRADE_TYPE = "condition_grade"
RESERVATION_STATUS_TYPE = "reservation_status"
RELEASE_REASON_TYPE = "release_reason"
RENTAL_STATUS_TYPE = "rental_status"
CHARGE_TYPE_TYPE = "charge_type"
CHARGE_STATUS_TYPE = "charge_status"
DAMAGE_SEVERITY_TYPE = "damage_severity"
DAMAGE_STATUS_TYPE = "damage_status"
NOTIFICATION_TYPE_TYPE = "notification_type"
NOTIFICATION_CHANNEL_TYPE = "notification_channel"
NOTIFICATION_STATUS_TYPE = "notification_status"
REVOKE_REASON_TYPE = "revoke_reason"

# Every enumeration keyed by the PostgreSQL type that stores it. The schema
# test walks this to compare the database with the classes above.
ENUMS_BY_TYPE_NAME: dict[str, type[DomainEnum]] = {
    USER_ROLE_TYPE: UserRole,
    CUSTOMER_TYPE_TYPE: CustomerType,
    ID_DOC_TYPE_TYPE: IdDocType,
    ACCOUNT_STATUS_TYPE: AccountStatus,
    ASSET_STATUS_TYPE: AssetStatus,
    CONDITION_GRADE_TYPE: ConditionGrade,
    RESERVATION_STATUS_TYPE: ReservationStatus,
    RELEASE_REASON_TYPE: ReleaseReason,
    RENTAL_STATUS_TYPE: RentalStatus,
    CHARGE_TYPE_TYPE: ChargeType,
    CHARGE_STATUS_TYPE: ChargeStatus,
    DAMAGE_SEVERITY_TYPE: DamageSeverity,
    DAMAGE_STATUS_TYPE: DamageStatus,
    NOTIFICATION_TYPE_TYPE: NotificationType,
    NOTIFICATION_CHANNEL_TYPE: NotificationChannel,
    NOTIFICATION_STATUS_TYPE: NotificationStatus,
    REVOKE_REASON_TYPE: RevokeReason,
}
