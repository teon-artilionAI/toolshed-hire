"""A customer's own statement for a period, read from the ledger (FR-28, US-27).

The statement is a record of what the ledger already holds, never a fresh
calculation. A hire line carries the deposit the ledger recorded when the
equipment went out and what has since been withheld or given back, and every
charge is the row that was raised. Nothing here recomputes a price, a late fee
or a deposit movement, so a statement cannot disagree with the hire it came
from.

A customer asks for their own statement and nobody else's. The profile is
found from the account that is signed in, and the hire query is filtered by
that profile in the database, so another customer's hire is never read
(BR-42).

The period is half open, `[from, to)`, like every other period in the system.
A hire belongs to the period when it went out in it, came back in it, or had
a charge raised in it, so a hire collected earlier but settled now still
appears. Every charge on a hire that belongs to the period is listed, even
one raised outside it, because the statement is about the hire and its money
as a whole.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.application.clock import Clock
from app.application.hire.read_models import ChargeDetail
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.enums import RentalStatus
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

PROFILE_NOT_FOUND_MESSAGE: Final[str] = "This account has no customer profile."
PERIOD_REVERSED_MESSAGE: Final[str] = "The end of the statement period has to be after its start."
PERIOD_TOO_LONG_MESSAGE: Final[str] = "A statement can cover at most ten years."
MAXIMUM_STATEMENT_DAYS: Final[int] = 3653
FROM_PARAMETER: Final[str] = "from"
TO_PARAMETER: Final[str] = "to"
NOTHING: Final[Decimal] = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class StatementQuery:
    """A customer's request for their own statement.

    Attributes:
        actor: The customer asking.
        starts_on: The first day of the period, which is included.
        ends_on: The day after the last day, which is excluded.

    """

    actor: Actor
    starts_on: date
    ends_on: date


@dataclass(frozen=True, slots=True)
class StatementLine:
    """One hire on a statement, with every charge raised on it.

    Attributes:
        rental_id: The hire's key.
        reference: The hire reference, for example TSH-H-26-000099.
        branch_code: The branch it went out from.
        branch_name: That branch's name.
        status: Where the hire stands.
        starts_on: The first day of hire.
        due_back_on: The day it was due back.
        checked_out_at: When it went out.
        returned_at: When the last unit came back, or None.
        deposit_held: The deposit the ledger recorded at checkout.
        deposit_withheld: How much of it has been kept.
        deposit_refunded: How much of it has been given back.
        balance_due: What the customer still owes on the hire.
        charges: Every money line on the hire, in the order raised.

    """

    rental_id: UUID
    reference: str
    branch_code: str
    branch_name: str
    status: RentalStatus
    starts_on: date
    due_back_on: date
    checked_out_at: datetime
    returned_at: datetime | None
    deposit_held: Decimal
    deposit_withheld: Decimal
    deposit_refunded: Decimal
    balance_due: Decimal
    charges: tuple[ChargeDetail, ...]

    @property
    def charges_total_inc_vat(self) -> Decimal:
        """Return the sum of every charge on the hire, VAT included."""
        return sum((charge.amount_inc_vat for charge in self.charges), NOTHING)


@dataclass(frozen=True, slots=True)
class StatementTotals:
    """The figures for the whole statement.

    Attributes:
        hire_count: How many hires the period holds.
        charges_total_inc_vat: Every charge on those hires, VAT included.
        deposit_held: Every deposit taken on them.
        deposit_withheld: Every deposit amount kept.
        deposit_refunded: Every deposit amount given back.
        balance_due: What the customer still owes across them.

    """

    hire_count: int
    charges_total_inc_vat: Decimal
    deposit_held: Decimal
    deposit_withheld: Decimal
    deposit_refunded: Decimal
    balance_due: Decimal


@dataclass(frozen=True, slots=True)
class Statement:
    """A customer's statement for one period.

    Attributes:
        customer_name: The name the customer is known by.
        customer_email: The address the account signs in with.
        starts_on: The first day of the period.
        ends_on: The day after the last day.
        generated_at: When the statement was read.
        lines: The hires that belong to the period, oldest first.
        totals: The figures over every line.

    """

    customer_name: str
    customer_email: str
    starts_on: date
    ends_on: date
    generated_at: datetime
    lines: tuple[StatementLine, ...]

    @property
    def totals(self) -> StatementTotals:
        """Return the totals over every line of the statement."""
        return StatementTotals(
            hire_count=len(self.lines),
            charges_total_inc_vat=sum(
                (line.charges_total_inc_vat for line in self.lines), NOTHING
            ),
            deposit_held=sum((line.deposit_held for line in self.lines), NOTHING),
            deposit_withheld=sum((line.deposit_withheld for line in self.lines), NOTHING),
            deposit_refunded=sum((line.deposit_refunded for line in self.lines), NOTHING),
            balance_due=sum((line.balance_due for line in self.lines), NOTHING),
        )


class ReadStatement(UseCase[StatementQuery, Statement]):
    """Read a customer's own statement from the ledger."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        """Keep the unit of work and the clock the statement is stamped with."""
        super().__init__(uow, clock)

    def execute(self, command: StatementQuery) -> Statement:
        """Return the statement, or refuse a period that cannot be read.

        Raises:
            NotFound: If the account has no customer profile.
            ValidationFailure: If the period is reversed or longer than ten
                years. The detail names `from` or `to`.

        """
        _ensure_period(command.starts_on, command.ends_on)
        actor = command.actor
        logger.info(
            "statement.read_started",
            extra={
                "user_id": str(actor.user_id),
                "from": command.starts_on.isoformat(),
                "to": command.ends_on.isoformat(),
            },
        )
        generated_at = self._clock.now()
        with self._uow as uow:
            details = uow.customers.details_for_account(actor.user_id)
            if details is None:
                raise NotFound(PROFILE_NOT_FOUND_MESSAGE)
            lines = uow.rentals.statement_for_customer(
                details.profile_id, command.starts_on, command.ends_on
            )
        statement = Statement(
            customer_name=details.full_name,
            customer_email=details.email,
            starts_on=command.starts_on,
            ends_on=command.ends_on,
            generated_at=generated_at,
            lines=lines,
        )
        logger.info(
            "statement.read_finished",
            extra={
                "user_id": str(actor.user_id),
                "hire_count": statement.totals.hire_count,
                "charge_count": sum(len(line.charges) for line in lines),
            },
        )
        return statement


def _ensure_period(starts_on: date, ends_on: date) -> None:
    """Refuse a period that is reversed or longer than ten years.

    Raises:
        ValidationFailure: Naming the bound that is wrong.

    """
    if ends_on <= starts_on:
        raise ValidationFailure(
            PERIOD_REVERSED_MESSAGE,
            {FROM_PARAMETER: starts_on.isoformat(), TO_PARAMETER: ends_on.isoformat()},
        )
    if (ends_on - starts_on).days > MAXIMUM_STATEMENT_DAYS:
        raise ValidationFailure(
            PERIOD_TOO_LONG_MESSAGE,
            {FROM_PARAMETER: starts_on.isoformat(), TO_PARAMETER: ends_on.isoformat()},
        )


__all__ = [
    "MAXIMUM_STATEMENT_DAYS",
    "ReadStatement",
    "Statement",
    "StatementLine",
    "StatementQuery",
    "StatementTotals",
]
