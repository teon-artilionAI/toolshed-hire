"""What an administrator asks of the catalogue, as the use cases are handed it (FR-22, US-30).

A creation names every field. An edit names only the fields the request sent,
and each of those arrives as a `Change`, so a field that was left out is told
apart from a field that was cleared. A field left out is None and keeps the
value it has. A field sent as null is `Change(None)` and is cleared, which only
the fields that may be empty allow.

The SKU of a model is not among the changes, because it never changes once the
model exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.domain.catalogue_entry_rules import ModelTerms
from app.domain.category_rules import CategoryTerms
from app.domain.identity import Actor


@dataclass(frozen=True, slots=True)
class Change[ValueT]:
    """The new value of one field that a request named.

    Attributes:
        value: What the field is to hold. None clears a field that may be empty.

    """

    value: ValueT


def chosen[ValueT](current: ValueT, change: Change[ValueT] | None) -> ValueT:
    """Return the new value when the field was named, and the current one when it was not."""
    return current if change is None else change.value


@dataclass(frozen=True, slots=True)
class NewCategoryCommand:
    """A request to create a category. A new category starts active.

    Attributes:
        actor: The administrator creating it.
        code: The short code.
        name: The display name.
        slug: The name it carries in an address.
        description: What it holds, or None.
        parent_category_id: The top level category it sits under, or None.
        sort_order: Where it sorts among its siblings.

    """

    actor: Actor
    code: str
    name: str
    slug: str
    description: str | None
    parent_category_id: UUID | None
    sort_order: int


@dataclass(frozen=True, slots=True)
class CategoryChanges:
    """The fields of a category an edit names, each None when it was left out."""

    code: Change[str] | None = None
    name: Change[str] | None = None
    slug: Change[str] | None = None
    description: Change[str | None] | None = None
    parent_category_id: Change[UUID | None] | None = None
    sort_order: Change[int] | None = None
    is_active: Change[bool] | None = None

    def applied_to(self, terms: CategoryTerms) -> CategoryTerms:
        """Return the terms with every named field changed and the rest as they were."""
        return CategoryTerms(
            code=chosen(terms.code, self.code),
            name=chosen(terms.name, self.name),
            slug=chosen(terms.slug, self.slug),
            description=chosen(terms.description, self.description),
            parent_category_id=chosen(terms.parent_category_id, self.parent_category_id),
            sort_order=chosen(terms.sort_order, self.sort_order),
            is_active=chosen(terms.is_active, self.is_active),
        )


@dataclass(frozen=True, slots=True)
class EditCategoryCommand:
    """A request to change some fields of a category.

    Attributes:
        actor: The administrator editing it.
        category_id: The category.
        changes: The fields the request named.

    """

    actor: Actor
    category_id: UUID
    changes: CategoryChanges


@dataclass(frozen=True, slots=True)
class NewModelCommand:
    """A request to create a product model. A new model starts unpublished.

    Attributes:
        actor: The administrator creating it.
        terms: Every field of the model.

    """

    actor: Actor
    terms: ModelTerms


@dataclass(frozen=True, slots=True)
class ModelChanges:
    """The fields of a model an edit names, each None when it was left out. Never the SKU.

    `is_published` may be among them, because the contract lets an edit carry
    every field of the model. It changes what the publication route changes.
    """

    name: Change[str] | None = None
    slug: Change[str] | None = None
    category_id: Change[UUID] | None = None
    manufacturer: Change[str] | None = None
    model_number: Change[str] | None = None
    short_description: Change[str] | None = None
    long_description: Change[str | None] | None = None
    daily_rate: Change[Decimal] | None = None
    weekly_rate: Change[Decimal] | None = None
    deposit_amount: Change[Decimal] | None = None
    late_fee_per_day: Change[Decimal] | None = None
    replacement_value: Change[Decimal] | None = None
    min_hire_days: Change[int] | None = None
    max_hire_days: Change[int] | None = None
    is_published: Change[bool] | None = None

    def applied_to(self, terms: ModelTerms) -> ModelTerms:
        """Return the terms with every named field changed and the rest as they were."""
        return ModelTerms(
            sku=terms.sku,
            name=chosen(terms.name, self.name),
            slug=chosen(terms.slug, self.slug),
            category_id=chosen(terms.category_id, self.category_id),
            manufacturer=chosen(terms.manufacturer, self.manufacturer),
            model_number=chosen(terms.model_number, self.model_number),
            short_description=chosen(terms.short_description, self.short_description),
            long_description=chosen(terms.long_description, self.long_description),
            daily_rate=chosen(terms.daily_rate, self.daily_rate),
            weekly_rate=chosen(terms.weekly_rate, self.weekly_rate),
            deposit_amount=chosen(terms.deposit_amount, self.deposit_amount),
            late_fee_per_day=chosen(terms.late_fee_per_day, self.late_fee_per_day),
            replacement_value=chosen(terms.replacement_value, self.replacement_value),
            min_hire_days=chosen(terms.min_hire_days, self.min_hire_days),
            max_hire_days=chosen(terms.max_hire_days, self.max_hire_days),
        )


@dataclass(frozen=True, slots=True)
class EditModelCommand:
    """A request to change some fields of a product model.

    Attributes:
        actor: The administrator editing it.
        model_id: The product model.
        changes: The fields the request named.

    """

    actor: Actor
    model_id: UUID
    changes: ModelChanges


@dataclass(frozen=True, slots=True)
class PublicationCommand:
    """A request to publish a product model or to take it out of the public catalogue.

    Attributes:
        actor: The administrator deciding.
        model_id: The product model.
        published: True to show it to visitors, False to hide it.

    """

    actor: Actor
    model_id: UUID
    published: bool
