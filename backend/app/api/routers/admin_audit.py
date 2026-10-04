"""The audit log, read by an administrator (FR-26, BR-49, BR-50).

`GET /api/admin/audit-events` answers one page of the log, newest first,
narrowed by `entityType`, `entityId`, `action`, `actorUserId` and a span of
business days, `from` and `to`, both included. Each event names the account
that acted, by its key, its name and the role it held at the time, and these
are null for an event the sweep wrote.

The route is read only, and there is no route that changes an audit event.
The database role the application runs as may insert into the table and read
it, and nothing else. Counter staff and customers are refused with 403.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.admin_deps import ReadAuditLogDependency
from app.api.admin_presenter import ADMIN_PREFIX, AUDIT_TAG, audit_page_response
from app.api.admin_schemas import ACTION_MAX_LENGTH, ENTITY_TYPE_MAX_LENGTH, AuditEventPageResponse
from app.api.booking_deps import actor_of
from app.api.deps import AdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import REFUSED_QUERY_RESPONSE
from app.application.admin_lists import (
    DEFAULT_PAGE_SIZE,
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.audit_reads import AuditLogRequest

router = APIRouter(prefix=ADMIN_PREFIX, tags=[AUDIT_TAG])


@router.get(
    "/audit-events",
    response_model=AuditEventPageResponse,
    summary="Return one page of the audit log, newest first",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_audit_events(
    user: AdminUser,
    reads: ReadAuditLogDependency,
    entity_type: Annotated[
        str | None,
        Query(
            alias="entityType",
            min_length=1,
            max_length=ENTITY_TYPE_MAX_LENGTH,
            description="Only events about this kind of record, for example `reservation`.",
        ),
    ] = None,
    entity_id: Annotated[
        UUID | None, Query(alias="entityId", description="Only events about this record.")
    ] = None,
    action: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=ACTION_MAX_LENGTH,
            description="Only events of this action, for example `charge.waived`.",
        ),
    ] = None,
    actor_user_id: Annotated[
        UUID | None,
        Query(alias="actorUserId", description="Only events this account made."),
    ] = None,
    from_day: Annotated[
        date | None,
        Query(alias="from", description="The first business day, which is included."),
    ] = None,
    to_day: Annotated[
        date | None,
        Query(alias="to", description="The last business day, which is included."),
    ] = None,
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many events a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> AuditEventPageResponse:
    """Return one page of the audit log, newest first.

    Raises:
        ValidationFailure: If `to` is before `from`. HTTP 422, naming `to`.

    """
    return audit_page_response(
        reads.page(
            AuditLogRequest(
                actor=actor_of(user),
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                from_day=from_day,
                to_day=to_day,
                page=page,
                page_size=page_size,
            )
        )
    )
