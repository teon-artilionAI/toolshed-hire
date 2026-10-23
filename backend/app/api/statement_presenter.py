"""Writing a statement in the shape the contract gives it (FR-28).

Nothing is worked out here. Every figure and every status was decided in the
application layer or read from the ledger, and this module only names the
fields the response schema expects.
"""

from __future__ import annotations

from app.api.statement_schemas import (
    StatementChargeResponse,
    StatementLineResponse,
    StatementResponse,
    StatementTotalsResponse,
)
from app.application.hire.statement import Statement


def statement_response(statement: Statement) -> StatementResponse:
    """Write a statement as the response contract gives it."""
    totals = statement.totals
    return StatementResponse(
        customer_name=statement.customer_name,
        customer_email=statement.customer_email,
        from_date=statement.starts_on,
        to_date=statement.ends_on,
        generated_at=statement.generated_at,
        totals=StatementTotalsResponse(
            hire_count=totals.hire_count,
            charges_total_inc_vat=totals.charges_total_inc_vat,
            deposit_held=totals.deposit_held,
            deposit_withheld=totals.deposit_withheld,
            deposit_refunded=totals.deposit_refunded,
            balance_due=totals.balance_due,
        ),
        items=[
            StatementLineResponse(
                rental_id=line.rental_id,
                reference=line.reference,
                branch_code=line.branch_code,
                branch_name=line.branch_name,
                status=line.status,
                from_date=line.starts_on,
                due_back_on=line.due_back_on,
                checked_out_at=line.checked_out_at,
                returned_at=line.returned_at,
                deposit_held=line.deposit_held,
                deposit_withheld=line.deposit_withheld,
                deposit_refunded=line.deposit_refunded,
                balance_due=line.balance_due,
                charges_total_inc_vat=line.charges_total_inc_vat,
                charges=[
                    StatementChargeResponse(
                        id=charge.id,
                        charge_type=charge.charge_type,
                        description=charge.description,
                        amount_ex_vat=charge.amount_ex_vat,
                        vat_amount=charge.vat_amount,
                        amount_inc_vat=charge.amount_inc_vat,
                        status=charge.status,
                        raised_at=charge.raised_at,
                        reverses_charge_id=charge.reverses_charge_id,
                    )
                    for charge in line.charges
                ],
            )
            for line in statement.lines
        ],
    )


__all__ = ["statement_response"]
