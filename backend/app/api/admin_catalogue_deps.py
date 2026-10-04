"""The dependencies of the admin catalogue, its reads and its five writes.

This is the part of the composition root behind the categories and the
product models of the admin console. The reads go through `SqlAdminCatalogue`
over the request scoped session, the way the two logs are wired in
`app/api/admin_deps.py`. Each write runs on the unit of work of the request and
reads its answer back through the same query object once it has committed,
which is the session the unit of work borrowed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, SessionDependency, UnitOfWorkDependency
from app.application.catalogue.admin_ports import AdminCatalogueQuery
from app.application.catalogue.admin_reads import ReadAdminCatalogue
from app.application.catalogue.manage_categories import (
    CreateCategoryUseCase,
    EditCategoryUseCase,
)
from app.application.catalogue.manage_models import CreateModelUseCase, EditModelUseCase
from app.application.catalogue.publish_model import PublishModelUseCase
from app.infrastructure.admin_catalogue_query import SqlAdminCatalogue


def get_admin_catalogue_query(session: SessionDependency) -> AdminCatalogueQuery:
    """Return the SQL admin catalogue over the request scoped session."""
    return SqlAdminCatalogue(session)


AdminCatalogueQueryDependency = Annotated[
    AdminCatalogueQuery, Depends(get_admin_catalogue_query)
]


def get_read_admin_catalogue(catalogue: AdminCatalogueQueryDependency) -> ReadAdminCatalogue:
    """Return the read of the admin catalogue."""
    return ReadAdminCatalogue(catalogue)


def get_create_category_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, catalogue: AdminCatalogueQueryDependency
) -> CreateCategoryUseCase:
    """Return the use case that creates a category."""
    return CreateCategoryUseCase(uow, clock, catalogue)


def get_edit_category_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, catalogue: AdminCatalogueQueryDependency
) -> EditCategoryUseCase:
    """Return the use case that edits a category."""
    return EditCategoryUseCase(uow, clock, catalogue)


def get_create_model_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, catalogue: AdminCatalogueQueryDependency
) -> CreateModelUseCase:
    """Return the use case that creates a product model."""
    return CreateModelUseCase(uow, clock, catalogue)


def get_edit_model_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, catalogue: AdminCatalogueQueryDependency
) -> EditModelUseCase:
    """Return the use case that edits a product model."""
    return EditModelUseCase(uow, clock, catalogue)


def get_publish_model_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, catalogue: AdminCatalogueQueryDependency
) -> PublishModelUseCase:
    """Return the use case that publishes or hides a product model."""
    return PublishModelUseCase(uow, clock, catalogue)


ReadAdminCatalogueDependency = Annotated[ReadAdminCatalogue, Depends(get_read_admin_catalogue)]
CreateCategory = Annotated[CreateCategoryUseCase, Depends(get_create_category_use_case)]
EditCategory = Annotated[EditCategoryUseCase, Depends(get_edit_category_use_case)]
CreateModel = Annotated[CreateModelUseCase, Depends(get_create_model_use_case)]
EditModel = Annotated[EditModelUseCase, Depends(get_edit_model_use_case)]
PublishModel = Annotated[PublishModelUseCase, Depends(get_publish_model_use_case)]
