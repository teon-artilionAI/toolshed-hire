"""A customer asking for everything held about them (FR-28, US-27, NFR-16).

The export is the POPIA right of access in a file. It reads the tables the
personal data map classifies as the customer's, through the profile and the
account, and writes one audit event in the same transaction (BR-49). The event
records that the export happened and how much was in it, never the values.

The file is JSON, named for the day it was made. It is built from the map
rather than a fixed list, so a table added in a later change joins the export
when the map classifies it. Credential columns are removed by the SQL
implementation before a row reaches this module, so a password hash or a
token hash can never be in a file a customer downloads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.application.audit import audit_event_for
from app.application.identity.export_ports import ExportedRows
from app.application.identity.profile import PROFILE_ENTITY_TYPE
from app.application.use_case import UseCase
from app.domain.errors import NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

EXPORTED_ACTION: Final[str] = "customer.data_exported"
EXPORTED_FORMAT_VERSION: Final[str] = "1"


@dataclass(frozen=True, slots=True)
class ExportMyDataQuery:
    """A customer asking for everything held about them.

    Attributes:
        actor: The customer asking.

    """

    actor: Actor


@dataclass(frozen=True, slots=True)
class ExportBundle:
    """Everything held about one customer.

    Attributes:
        customer_name: The name the customer is known by.
        customer_email: The address the account signs in with.
        generated_at: When the export was made.
        tables: The rows, by table name, in the order of the personal data map.
        row_count: How many rows in total.
        format_version: The version of this JSON shape.

    """

    customer_name: str
    customer_email: str
    generated_at: datetime
    tables: dict[str, ExportedRows]
    row_count: int
    format_version: str = EXPORTED_FORMAT_VERSION


class ExportMyData(UseCase[ExportMyDataQuery, ExportBundle]):
    """Read everything held about the signed in customer and audit the export."""

    def execute(self, command: ExportMyDataQuery) -> ExportBundle:
        """Return the customer's data, and record that it was exported.

        Raises:
            NotFound: If the account has no customer profile.

        """
        actor = command.actor
        now = self._clock.now()
        logger.info("customer.export_started", extra={"user_id": str(actor.user_id)})
        with self._uow as uow:
            details = uow.customers.details_for_account(actor.user_id)
            if details is None:
                raise NotFound("This account has no customer profile.")
            tables = dict(
                uow.personal_data_export.export(
                    customer_profile_id=details.profile_id,
                    user_account_id=actor.user_id,
                )
            )
            row_count = sum(len(rows) for rows in tables.values())
            uow.audit.record(
                audit_event_for(
                    actor=actor,
                    entity_type=PROFILE_ENTITY_TYPE,
                    entity_id=details.profile_id,
                    action=EXPORTED_ACTION,
                    occurred_at=now,
                    after_state={
                        "table_count": len(tables),
                        "row_count": row_count,
                    },
                )
            )
            uow.commit()
        logger.info(
            "customer.export_finished",
            extra={
                "user_id": str(actor.user_id),
                "table_count": len(tables),
                "row_count": row_count,
            },
        )
        return ExportBundle(
            customer_name=details.full_name,
            customer_email=details.email,
            generated_at=now,
            tables=tables,
            row_count=row_count,
        )


__all__ = [
    "EXPORTED_ACTION",
    "EXPORTED_FORMAT_VERSION",
    "ExportBundle",
    "ExportMyData",
    "ExportMyDataQuery",
]
