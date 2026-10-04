"""The dependencies of the admin operations, the two logs, the corrections and the release.

This is the part of the composition root behind the admin console's operations.
The two logs are reads, so their query objects are handed the request scoped
session and the request closes it, the way the report is wired in
`app/api/report_deps.py`. The re-send runs on the unit of work of the request,
sends through the dispatcher of `app/api/deps.py`, and reads the new
notification back through the log's query object. The charge corrections run
on the unit of work of the request with the late fee policy the rental is
shown with, and the force release on the unit of work alone.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import (
    ClockDependency,
    NotificationDispatcherDependency,
    SessionDependency,
    UnitOfWorkDependency,
)
from app.api.late_fee_deps import LateFeePolicyDependency
from app.application.audit_reads import ReadAuditLog
from app.application.booking.force_release import ForceReleaseUseCase
from app.application.hire.charge_corrections import (
    AdjustRentalUseCase,
    ReverseChargeUseCase,
    WaiveChargeUseCase,
)
from app.application.notification.log import NotificationLogQuery, ReadNotificationLog
from app.application.notification.resend import ResendNotificationUseCase
from app.infrastructure.audit_query import SqlAuditEventReads
from app.infrastructure.notification.log_query import SqlNotificationLog


def get_notification_log_query(session: SessionDependency) -> NotificationLogQuery:
    """Return the SQL notification log over the request scoped session."""
    return SqlNotificationLog(session)


NotificationLogQueryDependency = Annotated[
    NotificationLogQuery, Depends(get_notification_log_query)
]


def get_read_audit_log(session: SessionDependency) -> ReadAuditLog:
    """Return the read of the audit log, over its SQL query object."""
    return ReadAuditLog(SqlAuditEventReads(session))


def get_read_notification_log(log: NotificationLogQueryDependency) -> ReadNotificationLog:
    """Return the read of the notification log."""
    return ReadNotificationLog(log)


def get_resend_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    dispatcher: NotificationDispatcherDependency,
    log: NotificationLogQueryDependency,
) -> ResendNotificationUseCase:
    """Return the use case that sends a failed notification again."""
    return ResendNotificationUseCase(uow, clock, dispatcher, log)


def get_waive_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> WaiveChargeUseCase:
    """Return the use case that waives a charge."""
    return WaiveChargeUseCase(uow, clock, policy)


def get_reverse_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> ReverseChargeUseCase:
    """Return the use case that reverses a charge."""
    return ReverseChargeUseCase(uow, clock, policy)


def get_adjust_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> AdjustRentalUseCase:
    """Return the use case that adjusts a hire."""
    return AdjustRentalUseCase(uow, clock, policy)


def get_force_release_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> ForceReleaseUseCase:
    """Return the use case that releases one allocation by hand."""
    return ForceReleaseUseCase(uow, clock)


ReadAuditLogDependency = Annotated[ReadAuditLog, Depends(get_read_audit_log)]
ReadNotificationLogDependency = Annotated[ReadNotificationLog, Depends(get_read_notification_log)]
ResendNotification = Annotated[ResendNotificationUseCase, Depends(get_resend_use_case)]
WaiveCharge = Annotated[WaiveChargeUseCase, Depends(get_waive_use_case)]
ReverseCharge = Annotated[ReverseChargeUseCase, Depends(get_reverse_use_case)]
AdjustRental = Annotated[AdjustRentalUseCase, Depends(get_adjust_use_case)]
ForceRelease = Annotated[ForceReleaseUseCase, Depends(get_force_release_use_case)]
