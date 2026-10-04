"""Paths, members, bodies and helpers for the tests of user and role management and the holds.

The member sets are the ones the contract gives `AdminUser` and the answer to
a new account, and nothing else. A body is built in the camelCase names the
React client posts, as one that keeps every rule, and a test changes the one
member it is about.

`people_client` is the account client with the routes driven as a chosen
account on the still clock, so a test can open an account, read the link the
person was sent, choose a password through the reset route and sign in with
it. It works on the in memory database and on PostgreSQL alike.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from httpx import Response
from sqlmodel import Session, col, select

from app.infrastructure.models import AuditEvent, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.accounts_api import account_client
from tests.support.booking_api import BookingClient
from tests.support.clock import FixedClock
from tests.support.http import problem_of

USERS_PATH: Final[str] = "/api/admin/users"
CUSTOMERS_PATH: Final[str] = "/api/admin/customers"
STAFF_EMAIL: Final[str] = "thandi.mokoena@toolshedhire.co.za"
REASON: Final[str] = "Left the business at the end of September."
HOLD_REASON: Final[str] = "Paid what was owed and promised to collect on time."

ADMIN_USER_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "email", "fullName", "phone", "role", "branchCode", "isActive", "emailVerified",
        "lastLoginAt", "lockedUntil", "createdAt",
    }
)  # fmt: skip
CREATED_MEMBERS: Final[frozenset[str]] = frozenset({"user", "emailDeliverable"})
CUSTOMER_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "displayName", "email", "phone", "hasLogin", "emailVerified", "customerType",
        "companyName", "idDocumentType", "idDocumentLast4", "billingSuburb", "billingCity",
        "accountStatus", "tradeDiscountPercent", "noShowCount", "homeBranchCode",
    }
)  # fmt: skip


def user_path(user_id: object) -> str:
    """Return the path of one staff account."""
    return f"{USERS_PATH}/{user_id}"


def deactivation_path(user_id: object) -> str:
    """Return the path that deactivates a staff account."""
    return f"{user_path(user_id)}/deactivation"


def reactivation_path(user_id: object) -> str:
    """Return the path that reactivates a staff account."""
    return f"{user_path(user_id)}/reactivation"


def status_path(customer_id: object) -> str:
    """Return the path that sets the standing of a customer."""
    return f"{CUSTOMERS_PATH}/{customer_id}/status"


def staff_body(**members: object) -> dict[str, object]:
    """Return the body of a new counter assistant at CBD, with any member changed."""
    return {
        "email": STAFF_EMAIL,
        "fullName": "Thandi Mokoena",
        "phone": "082 441 7719",
        "role": "COUNTER_STAFF",
        "branchCode": "CBD",
        **members,
    }


def list_users(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the staff accounts as `account`."""
    return booking.client.get(USERS_PATH, params=params, headers=booking.headers(account))


def open_user(booking: BookingClient, account: UserAccount, body: dict[str, object]) -> Response:
    """Open a staff account as `account`."""
    return booking.client.post(USERS_PATH, json=body, headers=booking.headers(account))


def edit_user(
    booking: BookingClient, account: UserAccount, user_id: object, body: dict[str, object]
) -> Response:
    """Edit a staff account as `account`."""
    return booking.client.patch(user_path(user_id), json=body, headers=booking.headers(account))


def deactivate_user(
    booking: BookingClient, account: UserAccount, user_id: object, reason: object = REASON
) -> Response:
    """Deactivate a staff account as `account`."""
    return booking.client.post(
        deactivation_path(user_id), json={"reason": reason}, headers=booking.headers(account)
    )


def reactivate_user(booking: BookingClient, account: UserAccount, user_id: object) -> Response:
    """Reactivate a staff account as `account`."""
    return booking.client.post(reactivation_path(user_id), headers=booking.headers(account))


def list_customers(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the customers as `account`."""
    return booking.client.get(CUSTOMERS_PATH, params=params, headers=booking.headers(account))


def set_standing(
    booking: BookingClient,
    account: UserAccount,
    customer_id: object,
    standing: object,
    reason: object = HOLD_REASON,
) -> Response:
    """Set the standing of a customer as `account`."""
    return booking.client.post(
        status_path(customer_id),
        json={"accountStatus": standing, "reason": reason},
        headers=booking.headers(account),
    )


def refused_with(response: Response, status_code: int) -> dict[str, object]:
    """Return the problem document of a refusal, checking its status first."""
    assert response.status_code == status_code, response.text
    return problem_of(response)


def field_refused(response: Response) -> list[str]:
    """Return the fields a 422 names, checking its status first."""
    problem = refused_with(response, 422)
    errors = problem["errors"]
    assert isinstance(errors, dict)
    fields = errors["fields"]
    assert isinstance(fields, dict)
    return sorted(fields)


def actions_about(session: Session, entity_type: str) -> list[str]:
    """Return the action of every stored audit event about one kind of record, in order."""
    statement = (
        select(AuditEvent.action)
        .where(col(AuditEvent.entity_type) == entity_type)
        .order_by(col(AuditEvent.occurred_at), col(AuditEvent.id))
    )
    return list(session.exec(statement).all())


@contextmanager
def people_client(
    session: Session, clock: FixedClock, gateway: FakeEmailGateway
) -> Iterator[BookingClient]:
    """Yield the routes, sending through the gateway and hashing with real bcrypt."""
    with account_client(session, clock, gateway) as client:
        yield BookingClient(client, clock)


__all__ = [
    "ADMIN_USER_MEMBERS",
    "CREATED_MEMBERS",
    "CUSTOMERS_PATH",
    "CUSTOMER_MEMBERS",
    "HOLD_REASON",
    "REASON",
    "STAFF_EMAIL",
    "USERS_PATH",
    "actions_about",
    "deactivate_user",
    "edit_user",
    "field_refused",
    "list_customers",
    "list_users",
    "open_user",
    "people_client",
    "reactivate_user",
    "refused_with",
    "set_standing",
    "staff_body",
    "status_path",
]
