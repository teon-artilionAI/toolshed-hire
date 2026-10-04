"""Paths, members, bodies and helpers for the tests of the admin catalogue routes.

The member sets are the ones the contract gives `AdminCategory` and
`AdminModel`, and nothing else. A body is built in the camelCase names the
React client posts, as one that keeps every rule, and a test changes the one
member it is about. Money is written as a string, as the contract asks.

The routes are driven through `BookingClient`, which signs a request in as a
chosen account on the still clock, so these work on the in memory database
and on PostgreSQL alike.
"""

from __future__ import annotations

from typing import Final

from httpx import Response

from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient

CATEGORIES_PATH: Final[str] = "/api/admin/categories"
MODELS_PATH: Final[str] = "/api/admin/models"
DAILY_BEFORE: Final[str] = "280.00"
DAILY_AFTER: Final[str] = "310.00"

CATEGORY_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "code", "name", "slug", "description", "parentCategoryId", "parentName",
        "sortOrder", "isActive", "modelCount",
    }
)  # fmt: skip
MODEL_MEMBERS: Final[frozenset[str]] = frozenset(
    {
        "id", "sku", "name", "slug", "categoryId", "categoryName", "manufacturer", "modelNumber",
        "shortDescription", "longDescription", "dailyRate", "weeklyRate", "depositAmount",
        "lateFeePerDay", "replacementValue", "minHireDays", "maxHireDays", "isPublished",
        "assetCount", "updatedAt",
    }
)  # fmt: skip


def category_path(category_id: object) -> str:
    """Return the path of one category."""
    return f"{CATEGORIES_PATH}/{category_id}"


def model_path(model_id: object) -> str:
    """Return the path of one product model."""
    return f"{MODELS_PATH}/{model_id}"


def publication_path(model_id: object) -> str:
    """Return the path that publishes or hides a product model."""
    return f"{model_path(model_id)}/publication"


def category_body(**members: object) -> dict[str, object]:
    """Return the body of a new top level category, with any member changed."""
    return {
        "code": "PUMPS",
        "name": "Pumps and dewatering",
        "slug": "pumps-dewatering",
        "description": "Submersible and petrol pumps.",
        "parentCategoryId": None,
        "sortOrder": 20,
        **members,
    }


def model_body(category_id: object, **members: object) -> dict[str, object]:
    """Return the body of a new hammer at R280 a day in a category, with any member changed."""
    return {
        "sku": "DR-BOSCH-GBH226",
        "name": "Bosch GBH 2-26 DRE rotary hammer",
        "slug": "bosch-gbh-2-26-dre-rotary-hammer",
        "categoryId": str(category_id),
        "manufacturer": "Bosch",
        "modelNumber": "GBH 2-26 DRE",
        "shortDescription": "SDS-plus rotary hammer, 800 W.",
        "longDescription": None,
        "dailyRate": DAILY_BEFORE,
        "weeklyRate": "1120.00",
        "depositAmount": "600.00",
        "lateFeePerDay": "120.00",
        "replacementValue": "4200.00",
        "minHireDays": 1,
        "maxHireDays": 28,
        **members,
    }


def list_categories(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the categories as `account`."""
    return booking.client.get(CATEGORIES_PATH, params=params, headers=booking.headers(account))


def create_category(
    booking: BookingClient, account: UserAccount, body: dict[str, object]
) -> Response:
    """Create a category as `account`."""
    return booking.client.post(CATEGORIES_PATH, json=body, headers=booking.headers(account))


def edit_category(
    booking: BookingClient, account: UserAccount, category_id: object, body: dict[str, object]
) -> Response:
    """Edit a category as `account`."""
    return booking.client.patch(
        category_path(category_id), json=body, headers=booking.headers(account)
    )


def list_models(booking: BookingClient, account: UserAccount, **params: object) -> Response:
    """Read the product models as `account`."""
    return booking.client.get(MODELS_PATH, params=params, headers=booking.headers(account))


def read_model(booking: BookingClient, account: UserAccount, model_id: object) -> Response:
    """Read one product model as `account`."""
    return booking.client.get(model_path(model_id), headers=booking.headers(account))


def create_model(
    booking: BookingClient, account: UserAccount, body: dict[str, object]
) -> Response:
    """Create a product model as `account`."""
    return booking.client.post(MODELS_PATH, json=body, headers=booking.headers(account))


def edit_model(
    booking: BookingClient, account: UserAccount, model_id: object, body: dict[str, object]
) -> Response:
    """Edit a product model as `account`."""
    return booking.client.patch(model_path(model_id), json=body, headers=booking.headers(account))


def publish(
    booking: BookingClient, account: UserAccount, model_id: object, published: object
) -> Response:
    """Publish a product model, or take it out of the catalogue, as `account`."""
    return booking.client.post(
        publication_path(model_id), json={"published": published}, headers=booking.headers(account)
    )


__all__ = [
    "CATEGORIES_PATH",
    "CATEGORY_MEMBERS",
    "DAILY_AFTER",
    "DAILY_BEFORE",
    "MODELS_PATH",
    "MODEL_MEMBERS",
    "category_body",
    "category_path",
    "create_category",
    "create_model",
    "edit_category",
    "edit_model",
    "list_categories",
    "list_models",
    "model_body",
    "model_path",
    "publication_path",
    "publish",
    "read_model",
]
