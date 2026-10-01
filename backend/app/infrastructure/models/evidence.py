"""Evidence and supporting tables: AuditEvent, Notification and RateLimitCounter.

AuditEvent and RateLimitCounter are the two tables keyed by BIGSERIAL rather
than a UUID. Their `id` is None until the database has numbered the row.
"""

from __future__ import annotations

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from sqlalchemy import Column, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlmodel import Field, SQLModel

from app.domain.enums import (
    NOTIFICATION_CHANNEL_TYPE,
    NOTIFICATION_STATUS_TYPE,
    NOTIFICATION_TYPE_TYPE,
    USER_ROLE_TYPE,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    UserRole,
)
from app.infrastructure.models.columns import (
    bigserial_pk,
    created_at_column,
    enum_column,
    sha256_hex,
    small_int,
    timestamp,
    updated_at_column,
    uuid_column,
    uuid_fk,
    uuid_pk,
    varchar,
)


class AuditEvent(SQLModel, table=True):
    """An append only record of one state changing operation (BR-49).

    It is written in the same transaction as the change it describes and never
    updated, which is why it carries `occurred_at` and no created_at or
    updated_at. `entity_type` and `entity_id` name the row it describes without
    a foreign key, so the log outlives whatever it records.
    """

    __tablename__ = "audit_event"

    id: int | None = Field(default=None, sa_column=bigserial_pk())
    occurred_at: datetime | None = Field(
        default=None, sa_column=timestamp(nullable=False, default_now=True)
    )
    # Null for the lazy sweep, which has no human actor.
    actor_user_id: UUID | None = Field(
        default=None, sa_column=uuid_fk("user_account.id", nullable=True)
    )
    # Copied, so the log survives a later role change.
    actor_role: UserRole | None = Field(
        default=None, sa_column=enum_column(UserRole, USER_ROLE_TYPE, nullable=True)
    )
    entity_type: str = Field(sa_column=varchar(40))
    entity_id: UUID = Field(sa_column=uuid_column())
    action: str = Field(sa_column=varchar(60))
    # Only the fields that changed.
    before_state: dict[str, object] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    after_state: dict[str, object] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    # Correlates with the structured application log.
    request_id: UUID | None = Field(default=None, sa_column=uuid_column(nullable=True))
    ip_address: IPv4Address | IPv6Address | None = Field(
        default=None, sa_column=Column(INET, nullable=True)
    )


class Notification(SQLModel, table=True):
    """The record of an outbound booking confirmation email (BR-19).

    The row is written in the same transaction as the confirmation and sent
    only after commit, so a failed send is visible and can be sent again
    rather than being lost.
    """

    __tablename__ = "notification"

    id: UUID = Field(default_factory=uuid4, sa_column=uuid_pk())
    reservation_id: UUID = Field(sa_column=uuid_fk("reservation.id"))
    notification_type: NotificationType = Field(
        sa_column=enum_column(NotificationType, NOTIFICATION_TYPE_TYPE)
    )
    channel: NotificationChannel = Field(
        sa_column=enum_column(NotificationChannel, NOTIFICATION_CHANNEL_TYPE)
    )
    recipient_email: str = Field(sa_column=varchar(255))
    subject: str = Field(sa_column=varchar(200))
    status: NotificationStatus = Field(
        sa_column=enum_column(NotificationStatus, NOTIFICATION_STATUS_TYPE)
    )
    provider: str = Field(sa_column=varchar(20))
    # Returned by the provider on success.
    provider_message_id: str | None = Field(default=None, sa_column=varchar(80, nullable=True))
    attempts: int = Field(default=0, sa_column=small_int())
    last_error: str | None = Field(default=None, sa_column=varchar(300, nullable=True))
    queued_at: datetime = Field(sa_column=timestamp(nullable=False))
    sent_at: datetime | None = Field(default=None, sa_column=timestamp())
    created_at: datetime | None = Field(default=None, sa_column=created_at_column())
    updated_at: datetime | None = Field(default=None, sa_column=updated_at_column())


class RateLimitCounter(SQLModel, table=True):
    """One sliding window counter behind the sign in and booking rate limits.

    The seventeenth table. It has no foreign key, because the limiter has to
    count for an unauthenticated caller with no account row. The bucket key is
    hashed, so the table never holds an address or an identifier.
    """

    __tablename__ = "rate_limit_counter"
    __table_args__ = (
        UniqueConstraint(
            "bucket_key_hash", "window_started_at", name="uq_rate_limit_counter_bucket_window"
        ),
    )

    id: int | None = Field(default=None, sa_column=bigserial_pk())
    bucket_key_hash: str = Field(sa_column=sha256_hex(nullable=False))
    window_started_at: datetime = Field(sa_column=timestamp(nullable=False))
    request_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default=text("0"))
    )
