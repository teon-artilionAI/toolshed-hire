"""The liveness route, which must never touch the database (NFR-05, C-43).

An uptime check calls this every five minutes. If it opened a session, Neon's
compute would stay awake all month and the free allowance would be spent on a
check that is meant to be free. The test replaces the session provider with one
that fails, so a route that quietly depended on it could not pass.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.infrastructure.database import get_session
from app.main import app as production_app

LIVE_PATH: str = "/api/health/live"


def test_liveness_answers_from_the_process_alone() -> None:
    """The route answers 200 with the revision, and the session provider is never used."""

    def no_session() -> None:
        pytest.fail("The liveness route opened a database session.")

    production_app.dependency_overrides[get_session] = no_session
    try:
        with TestClient(production_app) as client:
            response = client.get(LIVE_PATH)
    finally:
        production_app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["environment"] == settings.environment.value
    assert body["revision"] == settings.revision


def test_liveness_is_public() -> None:
    """No token is needed."""
    with TestClient(production_app) as client:
        response = client.get(LIVE_PATH)
    assert response.status_code == 200
