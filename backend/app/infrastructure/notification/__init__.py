"""The notification module of the infrastructure layer.

`outbox` holds the SQL outbox over the `notification` table. `resend` holds the
adapter for the email provider. `gateways` holds the gateway that sends
nothing, the test double and the function that chooses between them.
"""

from __future__ import annotations

from app.infrastructure.notification.gateways import (
    FakeEmailGateway,
    UnconfiguredEmailGateway,
    build_notification_gateway,
)
from app.infrastructure.notification.outbox import SqlNotificationOutbox
from app.infrastructure.notification.resend import ResendEmailAdapter

__all__ = [
    "FakeEmailGateway",
    "ResendEmailAdapter",
    "SqlNotificationOutbox",
    "UnconfiguredEmailGateway",
    "build_notification_gateway",
]
