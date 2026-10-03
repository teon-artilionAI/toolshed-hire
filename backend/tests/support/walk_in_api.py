"""The body of a walk-in and the headers of a member of staff, for the walk-in tests.

A walk-in is posted to `POST /api/customers` in the camelCase names the React
client sends. The display name carries spaces round it on purpose, so every
test that registers one also proves the name is trimmed.
"""

from __future__ import annotations

from app.infrastructure.models import UserAccount
from tests.support.tokens import authorization_header, mint_access_token


def walk_in_body(**changes: object) -> dict[str, object]:
    """Return the body of a walk-in, with some members replaced."""
    body: dict[str, object] = {
        "displayName": "  Sizwe Ndlovu  ",
        "phone": "072 555 0199",
        "idDocumentType": "DRIVING_LICENCE",
        "idDocumentLast4": "7Q2B",
        "billingAddressLine1": "8 Station Road",
        "billingSuburb": "Observatory",
        "billingCity": "Cape Town",
        "billingPostalCode": "7925",
        "customerType": "INDIVIDUAL",
        "companyName": None,
        "vatNumber": None,
        "branchCode": None,
    }
    return {**body, **changes}


def headers_of(account: UserAccount) -> dict[str, str]:
    """Return the request headers of a signed in account."""
    return authorization_header(mint_access_token(account.id, role=account.role))


__all__ = ["headers_of", "walk_in_body"]
