"""The rules a category of the catalogue is held to when an administrator creates or edits it.

A category groups the catalogue for browsing and for the report. Nesting stops
at two levels, so a category is either at the top, or under a category that is
itself at the top, and nothing deeper. The database stops a category parenting
itself and cannot follow the chain any further, so the cap of two levels is a
rule here (FR-22).

Three things follow from the cap. A parent has no parent of its own. A
category is never its own parent. And a category that already has categories
under it cannot be placed under another one, because its children would then
be three levels down.

`checked_category_terms` holds the fields to their forms and widths, and
`ensure_parent_may_hold` holds the nesting. Creating a category and editing
one both go through the two, so the rules cannot differ between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.domain.catalogue_forms import (
    code_text,
    field_refusal,
    optional_text,
    required_text,
    slug_text,
)

CODE: Final[str] = "code"
NAME: Final[str] = "name"
SLUG: Final[str] = "slug"
DESCRIPTION: Final[str] = "description"
PARENT_CATEGORY_ID: Final[str] = "parent_category_id"
SORT_ORDER: Final[str] = "sort_order"
IS_ACTIVE: Final[str] = "is_active"

# The widths of the columns in the design document.
CODE_MAX_LENGTH: Final[int] = 16
NAME_MAX_LENGTH: Final[int] = 80
SLUG_MAX_LENGTH: Final[int] = 80
# A SMALLINT, and a place in a list is never below the first.
FIRST_SORT_ORDER: Final[int] = 0
LAST_SORT_ORDER: Final[int] = 32767
DEFAULT_SORT_ORDER: Final[int] = 0

SORT_ORDER_MESSAGE: Final[str] = (
    f"Enter a whole number from {FIRST_SORT_ORDER} to {LAST_SORT_ORDER}."
)
OWN_PARENT_MESSAGE: Final[str] = "A category cannot be placed under itself."
PARENT_NOT_AT_TOP_MESSAGE: Final[str] = (
    "Choose a top level category. Categories go two levels deep and no deeper."
)
HAS_CHILDREN_MESSAGE: Final[str] = (
    "This category has categories under it, so it has to stay at the top level."
)


@dataclass(frozen=True, slots=True)
class CategoryTerms:
    """What an administrator decides about a category.

    Attributes:
        code: The short code, for example `BREAK-DRILL`.
        name: The display name.
        slug: The name it carries in an address, for example `breaking-drilling`.
        description: What the category holds, or None.
        parent_category_id: The category it sits under, or None at the top.
        sort_order: Where it sorts among its siblings.
        is_active: False for a category taken out of the catalogue. It is
            never deleted (BR-51).

    """

    code: str
    name: str
    slug: str
    description: str | None
    parent_category_id: UUID | None
    sort_order: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class CatalogueCategory:
    """A stored category.

    Attributes:
        id: The category key.
        terms: What it is called, where it sits and whether it is active.

    """

    id: UUID
    terms: CategoryTerms

    @property
    def is_top_level(self) -> bool:
        """Return True when the category sits under no other."""
        return self.terms.parent_category_id is None


def checked_category_terms(terms: CategoryTerms) -> CategoryTerms:
    """Return the terms trimmed, or refuse the first field that breaks a rule.

    Raises:
        ValidationFailure: Naming the field, when the code or the slug is not
            of its form, when text is blank or too wide for its column, or
            when the sort order is out of range.

    """
    if not FIRST_SORT_ORDER <= terms.sort_order <= LAST_SORT_ORDER:
        raise field_refusal(SORT_ORDER, SORT_ORDER_MESSAGE)
    return CategoryTerms(
        code=code_text(CODE, terms.code, CODE_MAX_LENGTH),
        name=required_text(NAME, terms.name, NAME_MAX_LENGTH),
        slug=slug_text(SLUG, terms.slug, SLUG_MAX_LENGTH),
        description=optional_text(DESCRIPTION, terms.description, None),
        parent_category_id=terms.parent_category_id,
        sort_order=terms.sort_order,
        is_active=terms.is_active,
    )


def ensure_parent_may_hold(
    category_id: UUID | None, parent: CatalogueCategory, *, has_children: bool
) -> None:
    """Refuse a parent that would put a category more than two levels down.

    Args:
        category_id: The category being placed, or None for one not yet created.
        parent: The category it is to sit under.
        has_children: Whether the category being placed already has
            categories under it. Always False for a new one.

    Raises:
        ValidationFailure: Naming `parent_category_id`.

    """
    if category_id is not None and parent.id == category_id:
        raise field_refusal(PARENT_CATEGORY_ID, OWN_PARENT_MESSAGE)
    if not parent.is_top_level:
        raise field_refusal(PARENT_CATEGORY_ID, PARENT_NOT_AT_TOP_MESSAGE)
    if has_children:
        raise field_refusal(PARENT_CATEGORY_ID, HAS_CHILDREN_MESSAGE)
