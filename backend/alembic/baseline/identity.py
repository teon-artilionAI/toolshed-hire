"""Identity and access: branch, user_account, customer_profile and refresh_session.

The authentication identity is kept apart from hire behaviour. user_account
carries credentials and exactly one role. customer_profile carries the hire
side facts, and its link to an account is nullable so that a counter assistant
can register a walk-in who does not want a login.
"""

from __future__ import annotations

import logging
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

from .columns import (
    enum,
    flag,
    non_negative,
    percent,
    sha256_hex,
    small_int,
    timestamp,
    timestamps,
    uuid_column,
    uuid_fk,
    uuid_pk,
)

logger = logging.getLogger("alembic.baseline")

# Creation order. Dropped in reverse.
TABLES: Final[tuple[str, ...]] = (
    "branch",
    "user_account",
    "customer_profile",
    "refresh_session",
)


def create() -> None:
    """Create the four identity and access tables and their indexes."""
    _create_branch()
    _create_user_account()
    _create_customer_profile()
    _create_refresh_session()
    logger.info("Created identity and access tables: %s", ", ".join(TABLES))


def drop() -> None:
    """Drop the identity and access tables, children first."""
    for table in reversed(TABLES):
        op.drop_table(table)
    logger.info("Dropped identity and access tables: %s", ", ".join(reversed(TABLES)))


def _create_branch() -> None:
    """Create branch. There are exactly three rows, CBD, BLV and SMW."""
    op.create_table(
        "branch",
        uuid_pk(),
        sa.Column("code", sa.String(4), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("street_address", sa.String(160), nullable=False),
        sa.Column("suburb", sa.String(80), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("postal_code", sa.String(10), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        # The no-show sweep reads this to decide when a booking was missed.
        sa.Column("closes_at", sa.Time(), nullable=False),
        flag("is_active", default=True),
        *timestamps(),
    )


def _create_user_account() -> None:
    """Create user_account, the sign in identity."""
    op.create_table(
        "user_account",
        uuid_pk(),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        enum("user_role", "role"),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        uuid_fk("branch_id", "branch.id", nullable=True),
        flag("is_active", default=True),
        timestamp("email_verified_at"),
        timestamp("last_login_at"),
        small_int("failed_login_count"),
        timestamp("locked_until"),
        # The two account security emails carry a single use token. Only its
        # hash is stored, with the moment it stops being accepted.
        sha256_hex("email_verification_token_hash"),
        timestamp("email_verification_expires_at"),
        sha256_hex("password_reset_token_hash"),
        timestamp("password_reset_expires_at"),
        *timestamps(),
        # Only counter staff are branch scoped, and every one of them is. A
        # nullable column without this check could be used to create an
        # unscoped assistant.
        sa.CheckConstraint(
            "(role = 'COUNTER_STAFF') = (branch_id IS NOT NULL)",
            name="ck_user_account_branch_scope",
        ),
    )
    # A verification or reset link is looked up by the hash of its token. The
    # indexes are partial because almost every account has no token pending,
    # and unique so one token can never resolve to two accounts.
    for column in ("email_verification_token_hash", "password_reset_token_hash"):
        op.create_index(
            f"ux_user_account_{column}",
            "user_account",
            [column],
            unique=True,
            postgresql_where=sa.text(f"{column} IS NOT NULL"),
        )


def _create_customer_profile() -> None:
    """Create customer_profile and the two indexes behind the counter lookup."""
    op.create_table(
        "customer_profile",
        uuid_pk(),
        uuid_fk("user_account_id", "user_account.id", nullable=True, unique=True),
        enum("customer_type", "customer_type"),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("company_name", sa.String(120), nullable=True),
        sa.Column("vat_number", sa.String(20), nullable=True),
        enum("id_doc_type", "id_document_type"),
        # Only the last four digits are ever stored.
        sa.Column("id_document_last4", sa.CHAR(4), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=False),
        sa.Column("billing_address_line1", sa.String(120), nullable=False),
        sa.Column("billing_suburb", sa.String(80), nullable=False),
        sa.Column("billing_city", sa.String(80), nullable=False),
        sa.Column("billing_postal_code", sa.String(10), nullable=False),
        enum("account_status", "account_status"),
        percent("trade_discount_percent", default="0"),
        small_int("no_show_count"),
        # BR-16 records a late cancellation on the profile. The design document
        # states the rule and lists no column for it, so this is that column.
        small_int("late_cancellation_count"),
        uuid_fk("registered_branch_id", "branch.id"),
        *timestamps(),
        sa.CheckConstraint(
            "customer_type <> 'TRADE' OR company_name IS NOT NULL",
            name="ck_customer_profile_trade_company",
        ),
        non_negative("customer_profile", "discount", "trade_discount_percent"),
    )
    # A leading wildcard search on part of a name, which a btree cannot serve.
    op.create_index(
        "ix_customer_profile_display_name_trgm",
        "customer_profile",
        ["display_name"],
        postgresql_using="gin",
        postgresql_ops={"display_name": "gin_trgm_ops"},
    )
    op.create_index("ix_customer_profile_contact_phone", "customer_profile", ["contact_phone"])


def _create_refresh_session() -> None:
    """Create refresh_session, the server side record behind token rotation."""
    op.create_table(
        "refresh_session",
        uuid_pk(),
        uuid_fk("user_account_id", "user_account.id"),
        # Constant across a rotation chain, so a reused token revokes the lot.
        uuid_column("family_id"),
        sha256_hex("token_hash", nullable=False, unique=True),
        timestamp("issued_at", nullable=False),
        timestamp("expires_at", nullable=False),
        timestamp("rotated_at"),
        timestamp("revoked_at"),
        enum("revoke_reason", "revoked_reason", nullable=True),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        *timestamps(),
    )
    # The live sessions of one account. Partial, so revoked history is not in it.
    op.create_index(
        "ix_refresh_session_live",
        "refresh_session",
        ["user_account_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
