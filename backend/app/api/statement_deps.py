"""The dependencies of the statement and data export (FR-28, US-27).

Both use cases run on the request's unit of work and the process clock. The
exporter is reached through the unit of work itself, so this module only puts
the two collaborators together.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.application.hire.statement import ReadStatement
from app.application.identity.export_data import ExportMyData


def get_read_statement(uow: UnitOfWorkDependency, clock: ClockDependency) -> ReadStatement:
    """Return the use case that reads a customer's own statement."""
    return ReadStatement(uow, clock)


def get_export_my_data(uow: UnitOfWorkDependency, clock: ClockDependency) -> ExportMyData:
    """Return the use case that exports everything held about a customer."""
    return ExportMyData(uow, clock)


ReadStatementDependency = Annotated[ReadStatement, Depends(get_read_statement)]
ExportMyDataDependency = Annotated[ExportMyData, Depends(get_export_my_data)]
