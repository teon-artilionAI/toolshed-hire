"""Fixtures for the tests of the request middleware.

The applications here are built once per session. `create_app` installs the
logging configuration every time it runs, so building an application inside a
test would detach the log capture that test is reading. Built once and up
front, they cost nothing and disturb nothing.

None of these opens a database connection. The probe routes use no session,
and the applications are entered without their lifespan.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Environment
from tests.support.request_probe import build_request_probe_app, settings_for


@pytest.fixture(scope="session")
def request_probe_app() -> FastAPI:
    """Return the real application for the test environment, with the probe routes."""
    return build_request_probe_app()


@pytest.fixture
def request_probe_client(request_probe_app: FastAPI) -> TestClient:
    """Return a client for the probe application."""
    return TestClient(request_probe_app)


@pytest.fixture(scope="session")
def applications_by_environment() -> dict[Environment, FastAPI]:
    """Return the application each environment would run, built once each."""
    return {
        environment: build_request_probe_app(settings_for(environment))
        for environment in Environment
    }


@pytest.fixture
def client_for_environment(
    applications_by_environment: dict[Environment, FastAPI],
) -> Callable[[Environment], TestClient]:
    """Return a function giving a client for the application of an environment."""

    def _client(environment: Environment) -> TestClient:
        """Return a client for the application `environment` would run."""
        return TestClient(applications_by_environment[environment])

    return _client
