"""Response models for damage photographs, and the problem documents their routes answer with.

A photograph is described by its key, its report, its media type, its size and
when it was attached. Where it is stored never leaves the server. A list is
`{"items": [...]}` with no paging, because a report holds at most six
photographs and a hire at most six for each of its reports.

A link is `{"url": "...", "expiresAt": "..."}`. The URL is signed, works for five
minutes and is served as a download, and the browser opens it as it is.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import Field

from app.api.reservation_schemas import Timestamp
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.damage_photo import MAXIMUM_PHOTO_MEGABYTES, MAXIMUM_PHOTOS_PER_REPORT

PHOTOS_SWITCHED_OFF_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "Photographs are not switched on in this deployment.",
}
PHOTO_TOO_LARGE_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": f"The photograph is larger than {MAXIMUM_PHOTO_MEGABYTES} MB.",
}
UNSUPPORTED_PHOTO_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The body is not a JPEG or a PNG, by its media type or by its first bytes.",
}
PHOTO_LIMIT_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": f"The report already holds {MAXIMUM_PHOTOS_PER_REPORT} photographs.",
}
UNREADABLE_PHOTO_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The photograph could not be decoded, or holds more pixels than are kept.",
}
UNKNOWN_PHOTO_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such report, or it has no such photograph.",
}
UNKNOWN_HIRE_PHOTO_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such hire of yours, or no such photograph on it.",
}
BUSY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "Other photographs are being processed. Try again after `Retry-After`.",
}


class DamagePhotoResponse(CamelModel):
    """One photograph of a damage report."""

    id: UUID
    damage_report_id: UUID = Field(serialization_alias="damageReportId")
    damage_report_reference: str = Field(serialization_alias="damageReportReference")
    content_type: str = Field(serialization_alias="contentType")
    size_bytes: int = Field(serialization_alias="sizeBytes")
    uploaded_at: Timestamp = Field(serialization_alias="uploadedAt")


class DamagePhotoListResponse(CamelModel):
    """The photographs of one report, or of every report on one hire, oldest first."""

    items: list[DamagePhotoResponse]


class PhotoLinkResponse(CamelModel):
    """A signed link that opens one photograph as a download, for five minutes."""

    url: str
    expires_at: Timestamp = Field(serialization_alias="expiresAt")
