"""The dependencies of damage and quarantine, which are the report use cases and the reads.

This is the damage report part of the composition root. `app/api/deps.py`
wires the unit of work and the clock, and this module puts them together into
the use cases and the reads the damage report routes call. All of them run on
the unit of work of the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.application.hire.damage_closing import CloseDamageReportUseCase, SendForRepairUseCase
from app.application.hire.damage_reads import ReadDamageReports
from app.application.hire.file_damage_report import FileDamageReportUseCase


def get_file_damage_report_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> FileDamageReportUseCase:
    """Return the use case that files a damage report."""
    return FileDamageReportUseCase(uow, clock)


def get_send_for_repair_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> SendForRepairUseCase:
    """Return the use case that sends a report for repair."""
    return SendForRepairUseCase(uow, clock)


def get_close_damage_report_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> CloseDamageReportUseCase:
    """Return the use case that closes a report as resolved or written off."""
    return CloseDamageReportUseCase(uow, clock)


def get_read_damage_reports(uow: UnitOfWorkDependency) -> ReadDamageReports:
    """Return the reads of one report and of a page of them."""
    return ReadDamageReports(uow)


FileDamageReport = Annotated[FileDamageReportUseCase, Depends(get_file_damage_report_use_case)]
SendForRepair = Annotated[SendForRepairUseCase, Depends(get_send_for_repair_use_case)]
CloseDamageReport = Annotated[CloseDamageReportUseCase, Depends(get_close_damage_report_use_case)]
ReadDamageReportsDependency = Annotated[ReadDamageReports, Depends(get_read_damage_reports)]
