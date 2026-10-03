"""The committed API description is the one the application generates.

`backend/openapi.json` is what the frontend reads its types from, so a route,
a field or a status that changed in the code and not in the file would let the
two sides drift apart without anybody noticing. This compares the committed
file with what the application describes today and fails with the command that
writes it again.

The two are compared as parsed JSON, so the indentation and the line endings
of the file do not matter. Only what it says does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest

from app.main import app as production_app

OPENAPI_FILE: Final[Path] = Path(__file__).resolve().parents[2] / "openapi.json"
REGENERATE_COMMAND: Final[str] = (
    "ENVIRONMENT=test python -c \"import json, pathlib; from app.main import create_app; "
    "pathlib.Path('openapi.json').write_text(json.dumps(create_app().openapi(), indent=2) "
    "+ '\\n', encoding='utf-8')\""
)


def _differing_paths(committed: dict[str, object], generated: dict[str, object]) -> list[str]:
    """Return the routes whose description differs between the two documents."""
    committed_paths = committed.get("paths", {})
    generated_paths = generated.get("paths", {})
    assert isinstance(committed_paths, dict)
    assert isinstance(generated_paths, dict)
    names = set(committed_paths) | set(generated_paths)
    return sorted(name for name in names if committed_paths.get(name) != generated_paths.get(name))


def test_the_committed_document_is_the_one_the_application_generates() -> None:
    committed: dict[str, object] = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    generated: dict[str, object] = production_app.openapi()
    if committed != generated:
        pytest.fail(
            "backend/openapi.json is out of date with the application. Routes that differ: "
            f"{_differing_paths(committed, generated) or 'none, the schemas differ'}. Write "
            f"it again from the backend directory with\n{REGENERATE_COMMAND}\nand commit "
            "the result.",
            pytrace=False,
        )


def test_the_document_describes_the_account_and_profile_routes() -> None:
    paths = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))["paths"]
    for path in (
        "/api/auth/register",
        "/api/auth/email-verification",
        "/api/auth/email-verification/resend",
        "/api/auth/password-reset/request",
        "/api/auth/password-reset/complete",
        "/api/me/profile",
    ):
        assert path in paths
    assert set(paths["/api/me/profile"]) == {"get", "patch"}
