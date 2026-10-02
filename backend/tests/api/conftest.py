"""Fixtures for the tests of the request middleware.

The applications here are built once per session. `create_app` installs the
logging configuration every time it runs, so building an application inside a
test would detach the log capture that test is reading. Built once and up
front, they cost nothing and disturb nothing.

None of these opens a database connection. The probe routes use no session,
and the applications are entered without their lifespan.

`still_clock` and `auth_client` serve the session tests. They put the real
application on the in memory database with a clock the test moves, so a lock
or a lifetime can be run out without waiting for it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import Environment
from tests.support.clock import FixedClock
from tests.support.request_probe import build_request_probe_app, settings_for
from tests.support.sessions import session_client


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


@pytest.fixture
def still_clock() -> FixedClock:
    """Return a clock that stands still until the test moves it."""
    return FixedClock()


@pytest.fixture
def auth_client(session: Session, still_clock: FixedClock) -> Iterator[TestClient]:
    """Yield a client for the real application, on the in memory database and the still clock."""
    with session_client(session, still_clock) as client:
        yield client
