"""What the routes of the asset register share, the path key, the commands and the responses.

A request body becomes a command here and a read model becomes a response
here, once, so the router stays about its routes. Nothing is worked out in it
but the one thing the boundary owns, which is that a tag in a path is read in
capitals, the way it is painted on the unit.

An edit becomes a set of `Change`s, one for each field the request named, so
a field left out is told apart from a field sent as null.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Path

from app.api.admin_asset_schemas import (
    AdminAssetDetailResponse,
    AdminAssetPageResponse,
    AdminAssetResponse,
    AssetCreateRequest,
    AssetHistoryEntryResponse,
    AssetTransitionRequest,
    AssetUpdateRequest,
)
from app.api.admin_catalogue_presenter import cleared_or_sent, sent
from app.api.admin_catalogue_schemas import amount_of
from app.api.booking_deps import actor_of
from app.application.catalogue.asset_commands import (
    EditUnitCommand,
    MoveUnitCommand,
    RegisterUnitCommand,
    UnitChanges,
)
from app.application.catalogue.asset_read_models import (
    AdminAssetDetail,
    AdminAssetEntry,
    AdminAssetPage,
)
from app.domain import asset_register as unit_fields
from app.domain.asset_register import NewUnitTerms, UnitDetails
from app.infrastructure.models import UserAccount

# The tag of the router, which is the module the register belongs to.
CATALOGUE_TAG: Final[str] = "catalogue"
ASSETS_PATH: Final[str] = "/assets"
HISTORY_MEMBER: Final[str] = "history"

AssetPathTag = Annotated[str, Path(alias="tag", description="The tag painted on the unit.")]


def path_tag(tag: str) -> str:
    """Return a tag from a path as it is stored, trimmed and in capitals."""
    return tag.strip().upper()


def register_command(user: UserAccount, request: AssetCreateRequest) -> RegisterUnitCommand:
    """Return the command that registers the unit a request describes."""
    return RegisterUnitCommand(
        actor=actor_of(user),
        model_id=request.model_id,
        branch_code=request.branch_code,
        terms=NewUnitTerms(
            asset_tag=request.asset_tag,
            acquired_on=request.acquired_on,
            acquisition_cost=amount_of(request.acquisition_cost),
            details=UnitDetails(
                serial_number=request.serial_number,
                condition_grade=request.condition_grade,
                hour_meter_reading=request.hour_meter_reading,
                notes=request.notes,
            ),
        ),
    )


def edit_command(user: UserAccount, tag: str, request: AssetUpdateRequest) -> EditUnitCommand:
    """Return the command that changes the paperwork an edit named."""
    return EditUnitCommand(
        actor=actor_of(user),
        asset_tag=path_tag(tag),
        changes=UnitChanges(
            serial_number=cleared_or_sent(
                request, unit_fields.SERIAL_NUMBER, request.serial_number
            ),
            condition_grade=sent(request, unit_fields.CONDITION_GRADE, request.condition_grade),
            hour_meter_reading=cleared_or_sent(
                request, unit_fields.HOUR_METER_READING, request.hour_meter_reading
            ),
            notes=cleared_or_sent(request, unit_fields.NOTES, request.notes),
        ),
    )


def move_command(user: UserAccount, tag: str, request: AssetTransitionRequest) -> MoveUnitCommand:
    """Return the command that moves a unit to the status a request names."""
    return MoveUnitCommand(
        actor=actor_of(user), asset_tag=path_tag(tag), target=request.to, reason=request.reason
    )


def asset_response(entry: AdminAssetEntry) -> AdminAssetResponse:
    """Write one unit in the shape the contract gives `AdminAsset`."""
    return AdminAssetResponse(
        id=entry.id,
        asset_tag=entry.asset_tag,
        model_id=entry.model_id,
        model_name=entry.model_name,
        model_slug=entry.model_slug,
        category_name=entry.category_name,
        branch_code=entry.branch_code,
        branch_name=entry.branch_name,
        serial_number=entry.serial_number,
        status=entry.status,
        condition_grade=entry.condition_grade,
        acquired_on=entry.acquired_on,
        acquisition_cost=entry.acquisition_cost,
        hour_meter_reading=entry.hour_meter_reading,
        notes=entry.notes,
        retired_on=entry.retired_on,
        active_allocation_count=entry.active_allocation_count,
        open_damage_reports=entry.open_damage_reports,
        allowed_transitions=list(entry.allowed_transitions),
    )


def asset_detail_response(detail: AdminAssetDetail) -> AdminAssetDetailResponse:
    """Write one unit with its history, the newest first.

    The detail is `AdminAsset` with one member more, so it is built from the
    members of `asset_response` and the history, and the two cannot drift.
    """
    history = [
        AssetHistoryEntryResponse(
            at=entry.at, kind=entry.kind, summary=entry.summary, reference=entry.reference
        )
        for entry in detail.history
    ]
    return AdminAssetDetailResponse.model_validate(
        {**dict(asset_response(detail.entry)), HISTORY_MEMBER: history}
    )


def asset_page_response(page: AdminAssetPage) -> AdminAssetPageResponse:
    """Write one page of the units in the shape the contract gives a list."""
    return AdminAssetPageResponse(
        items=[asset_response(entry) for entry in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )
