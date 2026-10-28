"""How a damage photograph and a link to one are written in the shape of the contract.

The upload route and the four reads write photographs the same way, so the
mapping is here once. The object key on the read model is left behind.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Path

from app.api.damage_photo_schemas import (
    DamagePhotoListResponse,
    DamagePhotoResponse,
    PhotoLinkResponse,
)
from app.application.hire.damage_photo_models import DamagePhotoView, PhotoLink

PhotoPathKey = Annotated[UUID, Path(alias="photoId", description="The key of the photograph.")]


def photo_response(photo: DamagePhotoView) -> DamagePhotoResponse:
    """Write one photograph in the shape the contract gives it."""
    return DamagePhotoResponse(
        id=photo.id,
        damage_report_id=photo.damage_report_id,
        damage_report_reference=photo.damage_report_reference,
        content_type=photo.photo_format.content_type,
        size_bytes=photo.size_bytes,
        uploaded_at=photo.uploaded_at,
    )


def photo_list_response(photos: tuple[DamagePhotoView, ...]) -> DamagePhotoListResponse:
    """Write a list of photographs in the order the read returned them."""
    return DamagePhotoListResponse(items=[photo_response(photo) for photo in photos])


def link_response(link: PhotoLink) -> PhotoLinkResponse:
    """Write a link to one photograph."""
    return PhotoLinkResponse(url=link.url, expires_at=link.expires_at)
