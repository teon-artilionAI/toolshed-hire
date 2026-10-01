"""Identity and access: Branch, UserAccount, CustomerProfile and RefreshSession.

The authentication identity is kept apart from hire behaviour. UserAccount
carries credentials and exactly one role. CustomerProfile carries the hire side
facts, and its link to an account is nullable so that a counter assistant can
register a walk-in who does not want a login.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from sqlalchemy import CHAR, Column, Text, Time
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlmodel import Field, SQLModel

from app.domain.enums import (
    ACCOUNT_STATUS_TYPE,
    CUSTOMER_TYPE_TYPE,
    ID_DOC_TYPE_TYPE,
    REVOKE_REASON_TYPE,
    USER_ROLE_TYPE,
    AccountStatus,
    CustomerType,
    IdDocType,
    RevokeReason,
    UserRole,
)
from app.infrastructure.models.columns import (
    created_at_column,
    enum_column,
    flag,
    percent,
    sha256_hex,
    small_int,
    timestamp,
    updated_at_column,
    uuid_column,
    uuid_fk,
    uuid_pk,
    varchar,
)

BRANCH_CODE_MAX_LENGTH = 4
ID_DOCUMENT_DIGITS_KEPT = 4
NO_DISCOUNT = Decimal("0")


class Branch(SQLModel, table=True):
    """A physical trading location. There are exactly three, CBD, BLV and SMW."""

    __tablename__ = "branch"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    code: str = Field(sa_column=varchar(BRANCH_CODE_MAX_LENGTH, unique=True))
    name: str = Field(sa_column=varchar(80))
    street_address: str = Field(sa_column=varchar(160))
    suburb: str = Field(sa_column=varchar(80))
    city: str = Field(sa_column=varchar(80))
    postal_code: str = Field(sa_column=varchar(10))
    phone: str = Field(sa_column=varchar(20))
    opens_at: time = Field(sa_column=Column(Time, nullable=False))
    # The no-show sweep reads this to decide when a booking was missed (BR-17).
    closes_at: time = Field(sa_column=Column(Time, nullable=False))
    is_active: bool = Field(default=True, sa_column=flag(default=True))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class UserAccount(SQLModel, table=True):
    """The sign in identity. Carries exactly one role and nothing about hires.

    The role stored here is the only authority on what the holder may do. A
    role claim inside a token is never trusted, because a token issued before a
    demotion would otherwise outlive the demotion.

    The verification and reset columns hold the SHA-256 of a single use token
    and the moment it stops being accepted. The token itself is never stored.
    """

    __tablename__ = "user_account"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    email: str = Field(sa_column=Column(CITEXT(), nullable=False, unique=True))
    password_hash: str = Field(sa_column=Column(Text, nullable=False))
    role: UserRole = Field(sa_column=enum_column(UserRole, USER_ROLE_TYPE))
    full_name: str = Field(sa_column=varchar(120))
    phone: str | None = Field(default=None, sa_column=varchar(20, nullable=True))
    branch_id: UUID | None = Field(default=None, sa_column=uuid_fk("branch.id", nullable=True))
    is_active: bool = Field(default=True, sa_column=flag(default=True))
    email_verified_at: datetime | None = Field(default=None, sa_column=timestamp())
    last_login_at: datetime | None = Field(default=None, sa_column=timestamp())
    failed_login_count: int = Field(default=0, sa_column=small_int())
    locked_until: datetime | None = Field(default=None, sa_column=timestamp())
    email_verification_token_hash: str | None = Field(default=None, sa_column=sha256_hex())
    email_verification_expires_at: datetime | None = Field(default=None, sa_column=timestamp())
    password_reset_token_hash: str | None = Field(default=None, sa_column=sha256_hex())
    password_reset_expires_at: datetime | None = Field(default=None, sa_column=timestamp())
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class CustomerProfile(SQLModel, table=True):
    """The hire side facts about a customer, kept off the authentication record.

    `user_account_id` is null for a walk-in a counter assistant registered
    without a login. A reservation points here and not at the account, so a
    walk-in owns a booking history and the no-show count works for everyone.

    `late_cancellation_count` is where BR-16 records a late cancellation. The
    design document states the rule and lists no column for it.
    """

    __tablename__ = "customer_profile"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    user_account_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("user_account.id", nullable=True, unique=True)
    )
    customer_type: CustomerType = Field(sa_column=enum_column(CustomerType, CUSTOMER_TYPE_TYPE))
    display_name: str = Field(sa_column=varchar(120))
    # Required when the customer type is TRADE.
    company_name: str | None = Field(default=None, sa_column=varchar(120, nullable=True))
    vat_number: str | None = Field(default=None, sa_column=varchar(20, nullable=True))
    id_document_type: IdDocType = Field(sa_column=enum_column(IdDocType, ID_DOC_TYPE_TYPE))
    # Only the last four digits are ever stored.
    id_document_last4: str = Field(
        sa_column=Column(CHAR(ID_DOCUMENT_DIGITS_KEPT), nullable=False)
    )
    contact_phone: str = Field(sa_column=varchar(20))
    billing_address_line1: str = Field(sa_column=varchar(120))
    billing_suburb: str = Field(sa_column=varchar(80))
    billing_city: str = Field(sa_column=varchar(80))
    billing_postal_code: str = Field(sa_column=varchar(10))
    account_status: AccountStatus = Field(
        default=AccountStatus.ACTIVE, sa_column=enum_column(AccountStatus, ACCOUNT_STATUS_TYPE)
    )
    trade_discount_percent: Decimal = Field(default=NO_DISCOUNT, sa_column=percent(default="0"))
    no_show_count: int = Field(default=0, sa_column=small_int())
    late_cancellation_count: int = Field(default=0, sa_column=small_int())
    registered_branch_id: UUID = Field(sa_column=uuid_fk("branch.id"))
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class RefreshSession(SQLModel, table=True):
    """The server side record behind refresh token rotation (BR-48).

    `family_id` is constant across a rotation chain, so presenting a token that
    was already rotated can revoke every session descended from it.
    """

    __tablename__ = "refresh_session"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    user_account_id: UUID = Field(sa_column=uuid_fk("user_account.id"))
    family_id: UUID = Field(sa_column=uuid_column())
    token_hash: str = Field(sa_column=sha256_hex(nullable=False, unique=True))
    issued_at: datetime = Field(sa_column=timestamp(nullable=False))
    expires_at: datetime = Field(sa_column=timestamp(nullable=False))
    rotated_at: datetime | None = Field(default=None, sa_column=timestamp())
    revoked_at: datetime | None = Field(default=None, sa_column=timestamp())
    revoked_reason: RevokeReason | None = Field(
        default=None, sa_column=enum_column(RevokeReason, REVOKE_REASON_TYPE, nullable=True)
    )
    user_agent: str | None = Field(default=None, sa_column=varchar(200, nullable=True))
    ip_address: IPv4Address | IPv6Address | None = Field(
        default=None, sa_column=Column(INET, nullable=True)
    )
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())
