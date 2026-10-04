"""The signed in account as signing in, refreshing and `GET /api/me` all show it.

The three routes return one object, `UserResponse`, and this is the one place
it is put together, so they cannot drift apart in what they say about the
person who is signed in.

`emailDeliverable` is the email gateway's own rule for the account's address,
the rule the account routes already answer with. It depends on how the
gateway is configured and on the address, and on nothing else, so it costs no
statement and never calls the provider. The booking screen reads it so that it
does not promise a confirmation email this environment cannot deliver.
"""

from __future__ import annotations

from app.api.schemas import UserResponse, wire_role
from app.application.identity.sessions import SignedInAccount
from app.application.notification.ports import NotificationGateway


def user_response(account: SignedInAccount, gateway: NotificationGateway) -> UserResponse:
    """Return the account in the shape every session response and `/api/me` carry it in.

    Args:
        account: Who is signed in.
        gateway: The email gateway the application was built with. Only its
            rule for the address is asked. Nothing is sent.

    Returns:
        The account on the wire, with the role in its wire form and whether
        mail to its address would be handed to the provider.

    """
    return UserResponse(
        id=account.id,
        email=account.email,
        full_name=account.full_name,
        role=wire_role(account.role),
        branch_code=account.branch_code,
        email_verified=account.email_verified,
        email_deliverable=gateway.delivers_to(account.email),
    )
