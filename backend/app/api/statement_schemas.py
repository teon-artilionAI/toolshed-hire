"""Response models for a customer's statement and data export (FR-28, US-27).

Field names are camelCase, money is a string with two decimals, and a date is
`YYYY-MM-DD`, as everywhere else at this boundary. The statement carries the
ledger's own rows: every deposit movement and every charge is a value that was
stored, not a figure worked out again for the screen.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final
from uuid import UUID

from pydantic import Field

from app.api.catalogue_schemas import Money
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.enums import ChargeStatus, ChargeType, RentalStatus

STATEMENT_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The period is reversed or longer than ten years, or the account has no profile."
    ),
}
EXPORT_RESPONSE: Final[dict[str, object]] = {
    "description": (
        "Everything held about the signed in customer, as a JSON file. Credential columns are "
        "never included."
    ),
    "content": {"application/json": {"schema": {"type": "object"}}},
}


class StatementChargeResponse(CamelModel):
    """One money line on a statement."""

    id: UUID
    charge_type: ChargeType = Field(serialization_alias="chargeType")
    description: str
    amount_ex_vat: Money = Field(serialization_alias="amountExVat")
    vat_amount: Money = Field(serialization_alias="vatAmount")
    amount_inc_vat: Money = Field(serialization_alias="amountIncVat")
    status: ChargeStatus
    raised_at: datetime = Field(serialization_alias="raisedAt")
    reverses_charge_id: UUID | None = Field(serialization_alias="reversesChargeId")


class StatementLineResponse(CamelModel):
    """One hire on a statement, with every charge raised on it."""

    rental_id: UUID = Field(serialization_alias="rentalId")
    reference: str
    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    status: RentalStatus
    from_date: date = Field(serialization_alias="from")
    due_back_on: date = Field(serialization_alias="dueBackOn")
    checked_out_at: datetime = Field(serialization_alias="checkedOutAt")
    returned_at: datetime | None = Field(serialization_alias="returnedAt")
    deposit_held: Money = Field(serialization_alias="depositHeld")
    deposit_withheld: Money = Field(serialization_alias="depositWithheld")
    deposit_refunded: Money = Field(serialization_alias="depositRefunded")
    balance_due: Money = Field(serialization_alias="balanceDue")
    charges_total_inc_vat: Money = Field(serialization_alias="chargesTotalIncVat")
    charges: list[StatementChargeResponse]


class StatementTotalsResponse(CamelModel):
    """The figures over every line of a statement."""

    hire_count: int = Field(serialization_alias="hireCount")
    charges_total_inc_vat: Money = Field(serialization_alias="chargesTotalIncVat")
    deposit_held: Money = Field(serialization_alias="depositHeld")
    deposit_withheld: Money = Field(serialization_alias="depositWithheld")
    deposit_refunded: Money = Field(serialization_alias="depositRefunded")
    balance_due: Money = Field(serialization_alias="balanceDue")


class StatementResponse(CamelModel):
    """A customer's statement for one period."""

    customer_name: str = Field(serialization_alias="customerName")
    customer_email: str = Field(serialization_alias="customerEmail")
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    generated_at: datetime = Field(serialization_alias="generatedAt")
    totals: StatementTotalsResponse
    items: list[StatementLineResponse]
