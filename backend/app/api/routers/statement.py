"""The customer's statement and data export (FR-28, US-27, NFR-16).

`GET /api/me/statement` returns the signed in customer's own statement for a
period, as JSON, so the account screen can show it and print it.
`GET /api/me/statement.csv` returns the same statement as a CSV file, streamed
a line at a time. `GET /api/me/export` returns everything held about the
customer as a JSON file, built from the personal data map.

All three are for a customer and nobody else. The account is found from the
token, so there is no key in the request that could name another customer.
The statement routes refuse a period that is reversed or longer than ten
years, with a 422 naming the bound that is wrong. A staff account has no
customer profile and is told so, and a signed out caller is refused before
any of that.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.booking_deps import actor_of
from app.api.deps import CustomerUser
from app.api.identity_deps import never_store
from app.api.statement_csv import statement_csv_lines, statement_filename
from app.api.statement_deps import ExportMyDataDependency, ReadStatementDependency
from app.api.statement_presenter import statement_response
from app.api.statement_schemas import (
    EXPORT_RESPONSE,
    STATEMENT_REFUSED_RESPONSE,
    StatementResponse,
)
from app.application.hire.statement import MAXIMUM_STATEMENT_DAYS, StatementQuery
from app.application.identity.export_data import ExportMyDataQuery

STATEMENT_PATH: Final[str] = "/statement"
STATEMENT_CSV_PATH: Final[str] = "/statement.csv"
EXPORT_PATH: Final[str] = "/export"
CSV_MEDIA_TYPE: Final[str] = "text/csv; charset=utf-8"
JSON_MEDIA_TYPE: Final[str] = "application/json"
CONTENT_DISPOSITION_HEADER: Final[str] = "Content-Disposition"
EXPORT_FILENAME_PATTERN: Final[str] = "toolshed-my-data-{day}.json"

router = APIRouter(prefix="/me", tags=["identity"], dependencies=[Depends(never_store)])


@router.get(
    STATEMENT_PATH,
    response_model=StatementResponse,
    summary="Return the signed in customer's own statement for a period",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: STATEMENT_REFUSED_RESPONSE},
)
def read_statement(
    user: CustomerUser,
    reads: ReadStatementDependency,
    from_date: Annotated[date, Query(alias="from", description="The first day, included.")],
    to_date: Annotated[
        date,
        Query(alias="to", description="The day after the last day, so the period is [from, to)."),
    ],
) -> StatementResponse:
    """Return the statement, showing the ledger's own rows.

    Raises:
        ValidationFailure: If the period is reversed or longer than ten
            years. HTTP 422, naming `from` or `to`.

    """
    statement = reads.execute(
        StatementQuery(actor=actor_of(user), starts_on=from_date, ends_on=to_date)
    )
    return statement_response(statement)


@router.get(
    STATEMENT_CSV_PATH,
    response_class=StreamingResponse,
    summary="Return the statement as a CSV file",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: STATEMENT_REFUSED_RESPONSE},
)
def export_statement(
    user: CustomerUser,
    reads: ReadStatementDependency,
    from_date: Annotated[date, Query(alias="from", description="The first day, included.")],
    to_date: Annotated[
        date,
        Query(alias="to", description="The day after the last day, so the period is [from, to)."),
    ],
) -> StreamingResponse:
    """Return the same statement as a file a spreadsheet opens.

    Raises:
        ValidationFailure: As for the statement. HTTP 422.

    """
    statement = reads.execute(
        StatementQuery(actor=actor_of(user), starts_on=from_date, ends_on=to_date)
    )
    return StreamingResponse(
        statement_csv_lines(statement),
        media_type=CSV_MEDIA_TYPE,
        headers={
            CONTENT_DISPOSITION_HEADER: (
                f'attachment; filename="{statement_filename(statement)}"'
            )
        },
    )


@router.get(
    EXPORT_PATH,
    summary="Return everything held about the signed in customer as a JSON file",
    responses={status.HTTP_200_OK: EXPORT_RESPONSE},
)
def export_my_data(
    user: CustomerUser, exporter: ExportMyDataDependency
) -> JSONResponse:
    """Return the customer's data as a download and record that it was exported."""
    bundle = exporter.execute(ExportMyDataQuery(actor=actor_of(user)))
    body = {
        "formatVersion": bundle.format_version,
        "generatedAt": bundle.generated_at.isoformat(),
        "customer": {
            "name": bundle.customer_name,
            "email": bundle.customer_email,
        },
        "rowCount": bundle.row_count,
        "tables": bundle.tables,
    }
    filename = EXPORT_FILENAME_PATTERN.format(day=bundle.generated_at.date().isoformat())
    return JSONResponse(
        content=body,
        media_type=JSON_MEDIA_TYPE,
        headers={CONTENT_DISPOSITION_HEADER: f'attachment; filename="{filename}"'},
    )


__all__ = ["EXPORT_PATH", "MAXIMUM_STATEMENT_DAYS", "STATEMENT_CSV_PATH", "STATEMENT_PATH"]
