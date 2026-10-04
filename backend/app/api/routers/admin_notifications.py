"""The notification log and the re-send of a failed confirmation (FR-27, US-36).

`GET /api/admin/notifications` answers one page of every booking confirmation
the outbox holds, newest first, narrowed by `status`.

`POST /api/admin/notifications/{id}/resend` sends a FAILED notification again.
It writes a new notification for the same booking and address through the
outbox a confirmation goes through, sends it after the commit the way a
confirmation is sent, and answers 201 with the new one, whose `resendOf` names
the one that failed. The failed one is never changed, so both are in the log.
One that has not failed is a 409.

Both are for an administrator alone. Counter staff and customers are refused
with 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.admin_deps import ReadNotificationLogDependency, ResendNotification
from app.api.admin_presenter import (
    ADMIN_PREFIX,
    NOTIFICATION_TAG,
    NotificationPathKey,
    notification_page_response,
    notification_response,
)
from app.api.admin_schemas import (
    RESEND_REFUSED_RESPONSE,
    UNKNOWN_NOTIFICATION_RESPONSE,
    NotificationPageResponse,
    NotificationResponse,
)
from app.api.booking_deps import actor_of
from app.api.deps import AdminUser
from app.api.identity_deps import FreshAdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import REFUSED_QUERY_RESPONSE
from app.application.admin_lists import (
    DEFAULT_PAGE_SIZE,
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.notification.log import NotificationLogQueryRequest
from app.application.notification.resend import ResendCommand
from app.domain.enums import NotificationStatus

router = APIRouter(prefix=ADMIN_PREFIX, tags=[NOTIFICATION_TAG])


@router.get(
    "/notifications",
    response_model=NotificationPageResponse,
    summary="Return one page of the notification log, newest first",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_notifications(
    user: AdminUser,
    reads: ReadNotificationLogDependency,
    notification_status: Annotated[
        NotificationStatus | None,
        Query(alias="status", description="Only notifications in this status."),
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
            description="How many notifications a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> NotificationPageResponse:
    """Return one page of the notification log, newest first."""
    return notification_page_response(
        reads.page(
            NotificationLogQueryRequest(
                actor=actor_of(user), status=notification_status, page=page, page_size=page_size
            )
        )
    )


@router.post(
    "/notifications/{id}/resend",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a failed notification again, as a new notification",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_NOTIFICATION_RESPONSE,
        status.HTTP_409_CONFLICT: RESEND_REFUSED_RESPONSE,
    },
)
def post_resend(
    notification_id: NotificationPathKey, user: FreshAdminUser, use_case: ResendNotification
) -> NotificationResponse:
    """Queue the notification again, commit, send it and return the new one.

    Raises:
        NotFound: If there is no such notification. HTTP 404.
        StateTransitionError: If it has not failed. HTTP 409.

    """
    command = ResendCommand(actor=actor_of(user), notification_id=notification_id)
    return notification_response(use_case.execute(command))
