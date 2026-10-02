"""Grants for the restricted application role.

The design document describes two database roles. `toolshed_migrate` runs
these migrations. `toolshed_app` is what the running API connects as, and this
revision gives it its privileges on the baseline tables. It may select, insert
and update everywhere, with two exceptions. On `audit_event` it may select and
insert only, so the audit trail cannot be rewritten by the application that
writes it. On `rate_limit_counter` it may also delete, because expired windows
are removed there and nothing else is ever hard deleted.

The role is created by `scripts/provision_roles.py`, not here. If it does not
exist, this revision does nothing and logs that it skipped, so a plain local
database with one owner still migrates. To restrict the application on a
database that was migrated before the role existed, provision the role, then
downgrade to 0001 and upgrade again.

Any later migration that creates a table or a sequence must grant on it in the
same way, in the same revision. A privilege is not inherited by a new object,
so a table added without its grant is a table the application cannot read.

The statements live in `role_grants`, beside the `versions` directory, so the
test that proves the restriction applies exactly the grants this revision does.

Revision ID: 0002
Revises: 0001
Created: 2026-10-01
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

# The same arrangement as revision 0001. Alembic loads this file by its path,
# so the alembic directory is put on the import path from here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import role_grants

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Grant the application role its privileges, or skip if the role is absent."""
    role_grants.grant_application_privileges(op.get_bind())


def downgrade() -> None:
    """Revoke what the upgrade granted, or skip if the role is absent."""
    role_grants.revoke_application_privileges(op.get_bind())
