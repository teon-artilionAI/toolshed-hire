"""One finding from a pipeline artifact scan."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Finding:
    """One reason an artifact may not be published."""

    path: str
    line: int
    kind: str
    preview: str
