"""What the catalogue use cases share, which is how a change is recorded and how a refusal is named.

Every change to the catalogue writes one audit event in its own transaction
(BR-49). A creation records every field as it became. An edit records the
fields that changed and nothing else, each as it was and as it became, so the
event of a rate change says plainly that the daily rate went from 280.00 to
310.00. Money is written as text with two decimals and a key as text, so an
event never holds a float.

A refusal names its field the way the request did, `parentCategoryId` and not
`parent_category_id`, so a form can put the sentence beside the right input.
A code, a SKU or a slug that is already taken is refused the same way, whether
the use case found it first or the unique constraint did.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.application.identity.account_rules import refused_field, wire_name
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.domain import catalogue_entry_rules as model_fields
from app.domain import category_rules as category_fields
from app.domain.audit import StateValue
from app.domain.catalogue_entry_rules import ModelTerms
from app.domain.category_rules import CategoryTerms
from app.domain.errors import ValidationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

MONEY_TEXT: Final[str] = "{:.2f}"

type State = dict[str, StateValue]


def category_state(terms: CategoryTerms) -> State:
    """Return every field of a category as an audit event records it."""
    return {
        category_fields.CODE: terms.code,
        category_fields.NAME: terms.name,
        category_fields.SLUG: terms.slug,
        category_fields.DESCRIPTION: terms.description,
        category_fields.PARENT_CATEGORY_ID: _key_text(terms.parent_category_id),
        category_fields.SORT_ORDER: terms.sort_order,
        category_fields.IS_ACTIVE: terms.is_active,
    }


def model_state(terms: ModelTerms) -> State:
    """Return every field of a product model as an audit event records it."""
    return {
        model_fields.SKU: terms.sku,
        model_fields.NAME: terms.name,
        model_fields.SLUG: terms.slug,
        model_fields.CATEGORY_ID: str(terms.category_id),
        model_fields.MANUFACTURER: terms.manufacturer,
        model_fields.MODEL_NUMBER: terms.model_number,
        model_fields.SHORT_DESCRIPTION: terms.short_description,
        model_fields.LONG_DESCRIPTION: terms.long_description,
        model_fields.DAILY_RATE: _money_text(terms.daily_rate),
        model_fields.WEEKLY_RATE: _money_text(terms.weekly_rate),
        model_fields.DEPOSIT_AMOUNT: _money_text(terms.deposit_amount),
        model_fields.LATE_FEE_PER_DAY: _money_text(terms.late_fee_per_day),
        model_fields.REPLACEMENT_VALUE: _money_text(terms.replacement_value),
        model_fields.MIN_HIRE_DAYS: terms.min_hire_days,
        model_fields.MAX_HIRE_DAYS: terms.max_hire_days,
    }


def changed_fields(before: State, after: State) -> tuple[State, State]:
    """Return the fields whose value differs, as they were and as they became.

    Both are empty when nothing changed.
    """
    names = [name for name in after if before.get(name) != after[name]]
    return {name: before.get(name) for name in names}, {name: after[name] for name in names}


def record_change(
    uow: UnitOfWork,
    *,
    actor: Actor,
    entity_type: str,
    entity_id: UUID,
    action: str,
    now: datetime,
    before: Mapping[str, StateValue] | None,
    after: Mapping[str, StateValue],
) -> None:
    """Record the audit event of a change to the catalogue, in the transaction of the change."""
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            occurred_at=now,
            before_state=before,
            after_state=after,
        )
    )


def checked[TermsT](rule: Callable[[TermsT], TermsT], terms: TermsT) -> TermsT:
    """Return the terms a domain rule accepts, or its refusal named the way the request named it.

    Raises:
        ValidationFailure: Naming the field on the wire.

    """
    try:
        return rule(terms)
    except ValidationFailure as failure:
        raise refused_field(failure) from failure


def ensure_untaken(taken: frozenset[str], messages: Mapping[str, str]) -> None:
    """Refuse the first value another row already holds, in the order the messages are listed.

    Args:
        taken: The fields whose value is already held elsewhere.
        messages: The sentence for each field that can be taken, in the order
            they are checked.

    Raises:
        ValidationFailure: Naming the field on the wire.

    """
    for field, message in messages.items():
        if field in taken:
            logger.info("catalogue.value_taken", extra={"field": field})
            raise refused(wire_name(field), message)


def refused_duplicate(
    duplicate: DuplicateCatalogueValue, messages: Mapping[str, str]
) -> ValidationFailure:
    """Return the refusal of a value the unique constraint found taken, after the check missed it.

    The check and the insert are not atomic, so a second administrator can
    take a value between them. The constraint refuses the row, and the
    answer is the same sentence the check would have given.
    """
    logger.warning(
        "catalogue.value_taken_in_a_race",
        extra={"field": duplicate.field, "attempted": "write a catalogue row"},
    )
    return refused(wire_name(duplicate.field), messages[duplicate.field])


def _key_text(key: UUID | None) -> str | None:
    """Return a key as text, or None."""
    return str(key) if key is not None else None


def _money_text(amount: Decimal) -> str:
    """Return an amount as text with two decimals."""
    return MONEY_TEXT.format(amount)
