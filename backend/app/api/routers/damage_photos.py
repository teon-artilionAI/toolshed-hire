"""The photograph routes of a damage report, which are #83 and the owner's half of #112.

`POST /api/damage-reports/{id}/photos` attaches one photograph, sent as the
raw body with `Content-Type: image/jpeg` or `image/png`. Counter staff of the
branch that holds the unit may, and an administrator at any branch (BR-43). It
answers 201 with the photograph, 413 past 4 MB, 415 for anything that is not a
JPEG or a PNG by its first bytes, 409 for a seventh photograph and 422 for a
photograph that cannot be decoded.

`GET /api/damage-reports/{id}/photos` lists the photographs of a report and
`GET /api/damage-reports/{id}/photos/{photoId}` answers with a link that opens
one of them for five minutes, as a download. Both are for staff, at any branch,
as the report itself is. A customer is refused with 403 by role, and reads the
photographs of their own hire through `/api/me/rentals`.

Every one of these answers 503 while photographs are switched off, before it
reads a body or the database.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.booking_deps import actor_of
from app.api.damage_photo_deps import (
    PhotosSwitchedOn,
    ReadDamagePhotosDependency,
    UploadDamagePhoto,
)
from app.api.damage_photo_presenter import (
    PhotoPathKey,
    link_response,
    photo_list_response,
    photo_response,
)
from app.api.damage_photo_schemas import (
    BUSY_RESPONSE,
    PHOTO_LIMIT_RESPONSE,
    PHOTO_TOO_LARGE_RESPONSE,
    PHOTOS_SWITCHED_OFF_RESPONSE,
    UNKNOWN_PHOTO_RESPONSE,
    UNREADABLE_PHOTO_RESPONSE,
    UNSUPPORTED_PHOTO_RESPONSE,
    DamagePhotoListResponse,
    DamagePhotoResponse,
    PhotoLinkResponse,
)
from app.api.damage_presenter import DAMAGE_REPORTS_PREFIX, ReportPathKey
from app.api.damage_schemas import UNKNOWN_REPORT_RESPONSE
from app.api.deps import CounterUser
from app.api.hire_presenter import HIRE_TAG
from app.api.photo_body import PHOTO_REQUEST_BODY, PhotoBody
from app.api.reservation_schemas import NOT_PERMITTED_RESPONSE
from app.application.hire.damage_models import DamageReportKey
from app.application.hire.upload_damage_photo import UploadDamagePhotoCommand

router = APIRouter(prefix=DAMAGE_REPORTS_PREFIX, tags=[HIRE_TAG])


@router.post(
    "/{id}/photos",
    response_model=DamagePhotoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a JPEG or PNG photograph to a damage report",
    openapi_extra=PHOTO_REQUEST_BODY,
    responses={
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_REPORT_RESPONSE,
        status.HTTP_409_CONFLICT: PHOTO_LIMIT_RESPONSE,
        status.HTTP_413_CONTENT_TOO_LARGE: PHOTO_TOO_LARGE_RESPONSE,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: UNSUPPORTED_PHOTO_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: UNREADABLE_PHOTO_RESPONSE,
        status.HTTP_429_TOO_MANY_REQUESTS: BUSY_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: PHOTOS_SWITCHED_OFF_RESPONSE,
    },
)
def post_damage_photo(
    report_key: ReportPathKey,
    user: CounterUser,
    _switched_on: PhotosSwitchedOn,
    content: PhotoBody,
    use_case: UploadDamagePhoto,
) -> DamagePhotoResponse:
    """Check, re-encode, store and record one photograph.

    Raises:
        PhotoTooLarge: Past 4 MB. HTTP 413.
        UnsupportedPhoto: Not a JPEG or a PNG. HTTP 415.
        NotFound: If there is no such report. HTTP 404.
        BranchScopeError: If counter staff attach it at another branch. HTTP 403.
        PhotoLimitReached: If the report holds six already. HTTP 409.
        ValidationFailure: If it cannot be decoded or holds too many pixels. HTTP 422.
        FeatureSwitchedOff: If photographs are switched off. HTTP 503.

    """
    photo = use_case.execute(
        UploadDamagePhotoCommand(
            actor=actor_of(user), key=DamageReportKey.parse(report_key), content=content
        )
    )
    return photo_response(photo)


@router.get(
    "/{id}/photos",
    response_model=DamagePhotoListResponse,
    summary="List the photographs of a damage report, oldest first",
    responses={
        status.HTTP_404_NOT_FOUND: UNKNOWN_REPORT_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: PHOTOS_SWITCHED_OFF_RESPONSE,
    },
)
def list_damage_photos(
    report_key: ReportPathKey,
    user: CounterUser,
    _switched_on: PhotosSwitchedOn,
    reads: ReadDamagePhotosDependency,
) -> DamagePhotoListResponse:
    """Return every photograph of the report.

    Raises:
        NotFound: If there is no such report. HTTP 404.
        FeatureSwitchedOff: If photographs are switched off. HTTP 503.

    """
    photos = reads.of_report(actor_of(user), DamageReportKey.parse(report_key))
    return photo_list_response(photos)


@router.get(
    "/{id}/photos/{photoId}",
    response_model=PhotoLinkResponse,
    summary="Return a five minute link that opens one photograph of a damage report",
    responses={
        status.HTTP_404_NOT_FOUND: UNKNOWN_PHOTO_RESPONSE,
        status.HTTP_503_SERVICE_UNAVAILABLE: PHOTOS_SWITCHED_OFF_RESPONSE,
    },
)
def read_damage_photo_link(
    report_key: ReportPathKey,
    photo_id: PhotoPathKey,
    user: CounterUser,
    _switched_on: PhotosSwitchedOn,
    reads: ReadDamagePhotosDependency,
) -> PhotoLinkResponse:
    """Return a signed link to the photograph, served as a download.

    Raises:
        NotFound: If there is no such report or photograph. HTTP 404.
        FeatureSwitchedOff: If photographs are switched off. HTTP 503.

    """
    link = reads.link(actor_of(user), DamageReportKey.parse(report_key), photo_id)
    return link_response(link)
