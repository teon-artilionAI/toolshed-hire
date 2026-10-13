"""What the photograph use cases are asked with and hand back, as small frozen dataclasses.

`PhotoTarget` is what attaching a photograph needs to know about the report,
which is its key, its reference, the branch that holds the unit and how many
photographs it already has. `DamagePhotoView` is one photograph as a reader
sees it, and `PhotoLink` the short lived link that opens it.

The object key is carried so the link can be made, and it never leaves the
server. A reader is given the photograph's own key and a link that expires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.damage_photo import PhotoFormat


@dataclass(frozen=True, slots=True)
class PhotoTarget:
    """The damage report a photograph is being attached to.

    Attributes:
        report_id: The report key.
        reference: Its reference, for example TSH-D-26-00031.
        branch_id: The branch that holds the damaged unit, which is the branch
            whose counter may attach photographs (BR-43).
        photos_held: How many photographs the report has already.

    """

    report_id: UUID
    reference: str
    branch_id: UUID
    photos_held: int


@dataclass(frozen=True, slots=True)
class DamagePhotoView:
    """One photograph of a damage report, as staff or the customer read it.

    Attributes:
        id: The photograph's key.
        damage_report_id: The report it belongs to.
        damage_report_reference: That report's reference.
        object_key: Where it is stored. Kept on the server.
        photo_format: Whether it is a JPEG or a PNG.
        size_bytes: How large the stored copy is.
        uploaded_at: When it was attached.

    """

    id: UUID
    damage_report_id: UUID
    damage_report_reference: str
    object_key: str
    photo_format: PhotoFormat
    size_bytes: int
    uploaded_at: datetime

    @property
    def download_name(self) -> str:
        """Return the file name a downloaded copy is saved under."""
        return (
            f"{self.damage_report_reference}-{str(self.id)[:8]}.{self.photo_format.extension}"
        )


@dataclass(frozen=True, slots=True)
class PhotoLink:
    """A link that opens one photograph for a short while.

    Attributes:
        url: The signed address of the photograph, served as a download.
        expires_at: When the link stops working.

    """

    url: str
    expires_at: datetime
