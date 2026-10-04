"""The dependencies of the asset register, its reads and its three writes.

This is the part of the composition root behind the asset register of the
admin console. The reads go through `SqlAssetRegister` over the request scoped
session, the way the admin catalogue is wired in
`app/api/admin_catalogue_deps.py`. Each write runs on the unit of work of the
request and reads its answer back through the same query object once it has
committed, which is the session the unit of work borrowed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, SessionDependency, UnitOfWorkDependency
from app.application.catalogue.asset_ports import AssetRegisterQuery
from app.application.catalogue.asset_reads import ReadAssetRegister
from app.application.catalogue.move_asset import MoveUnitUseCase
from app.application.catalogue.register_asset import EditUnitUseCase, RegisterUnitUseCase
from app.infrastructure.asset_register_query import SqlAssetRegister


def get_asset_register_query(session: SessionDependency) -> AssetRegisterQuery:
    """Return the SQL asset register over the request scoped session."""
    return SqlAssetRegister(session)


AssetRegisterQueryDependency = Annotated[AssetRegisterQuery, Depends(get_asset_register_query)]


def get_read_asset_register(register: AssetRegisterQueryDependency) -> ReadAssetRegister:
    """Return the read of the asset register."""
    return ReadAssetRegister(register)


def get_register_unit_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, register: AssetRegisterQueryDependency
) -> RegisterUnitUseCase:
    """Return the use case that registers a unit."""
    return RegisterUnitUseCase(uow, clock, register)


def get_edit_unit_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, register: AssetRegisterQueryDependency
) -> EditUnitUseCase:
    """Return the use case that edits the paperwork of a unit."""
    return EditUnitUseCase(uow, clock, register)


def get_move_unit_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, register: AssetRegisterQueryDependency
) -> MoveUnitUseCase:
    """Return the use case that moves a unit through its lifecycle by hand."""
    return MoveUnitUseCase(uow, clock, register)


ReadAssetRegisterDependency = Annotated[ReadAssetRegister, Depends(get_read_asset_register)]
RegisterUnit = Annotated[RegisterUnitUseCase, Depends(get_register_unit_use_case)]
EditUnit = Annotated[EditUnitUseCase, Depends(get_edit_unit_use_case)]
MoveUnit = Annotated[MoveUnitUseCase, Depends(get_move_unit_use_case)]
