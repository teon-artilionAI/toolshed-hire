"""A photograph store that keeps everything in memory, for the tests of damage photographs.

It stands where the private bucket stands in a deployment. It keeps what it was
given under the name it was given, refuses a name already in use as the bucket
does with `if_generation_match=0`, and hands out a link shaped like a V4 signed
URL on storage.googleapis.com, so a test can read the lifetime and the
disposition the link was asked for. No network is touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Final
from urllib.parse import quote

TEST_BUCKET: Final[str] = "toolshed-test-damage-photos"
STORAGE_ORIGIN: Final[str] = "https://storage.googleapis.com"


@dataclass(frozen=True, slots=True)
class StoredPhoto:
    """One object of the store.

    Attributes:
        content: The bytes stored, which are the re-encoded photograph.
        content_type: The media type it was stored as.

    """

    content: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class LinkRequest:
    """One link the store was asked for.

    Attributes:
        object_key: The object the link opens.
        file_name: The name the download is saved under.
        lifetime: How long the link works.

    """

    object_key: str
    file_name: str
    lifetime: timedelta


@dataclass
class MemoryPhotoStore:
    """A bucket in a dictionary.

    Attributes:
        objects: Every object stored, by its name.
        links: Every link handed out, in order.

    """

    objects: dict[str, StoredPhoto] = field(default_factory=dict)
    links: list[LinkRequest] = field(default_factory=list)

    @property
    def switched_on(self) -> bool:
        """Return True, because this store keeps photographs."""
        return True

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        """Keep the object, refusing a name already in use.

        Raises:
            RuntimeError: If an object of that name is stored already.

        """
        if object_key in self.objects:
            raise RuntimeError(f"An object named {object_key} is already in the test bucket.")
        self.objects[object_key] = StoredPhoto(content=content, content_type=content_type)

    def download_link(self, object_key: str, *, file_name: str, lifetime: timedelta) -> str:
        """Return a link shaped like a signed URL, for an object that is stored.

        Raises:
            KeyError: If no object of that name is stored.

        """
        if object_key not in self.objects:
            raise KeyError(f"No object named {object_key} is in the test bucket.")
        self.links.append(LinkRequest(object_key, file_name, lifetime))
        disposition = quote(f'attachment; filename="{file_name}"')
        return (
            f"{STORAGE_ORIGIN}/{TEST_BUCKET}/{object_key}?X-Goog-Algorithm=GOOG4-RSA-SHA256"
            f"&X-Goog-Expires={int(lifetime.total_seconds())}"
            f"&response-content-disposition={disposition}&X-Goog-Signature=test"
        )

    def only_object(self) -> tuple[str, StoredPhoto]:
        """Return the one object stored, failing when there is not exactly one."""
        assert len(self.objects) == 1, sorted(self.objects)
        ((key, stored),) = self.objects.items()
        return key, stored


__all__ = ["STORAGE_ORIGIN", "TEST_BUCKET", "LinkRequest", "MemoryPhotoStore", "StoredPhoto"]
