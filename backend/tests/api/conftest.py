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

`booking` serves the reservation tests the same way. It drives the six
reservation routes on that clock, so a hold can be run out in a line, and it
sends through the fake gateway of the `email_gateway` fixture, so a test can
read what was sent.

`account_api` and `home_branch` serve the tests of registration, the two
account links and the profile. The client sends through the same fake gateway
and hashes each distinct password once for the whole run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.deps import get_notification_gateway
from app.config import Environment
from app.infrastructure.models import Branch
from app.infrastructure.notification import FakeEmailGateway
from app.main import app as production_app
from tests.support.accounts_api import HOME_BRANCH_CODE, account_client
from tests.support.booking_api import BookingClient
from tests.support.clock import FixedClock
from tests.support.factories import Factory
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


@pytest.fixture
def booking(
    session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
) -> Iterator[BookingClient]:
    """Yield the reservation routes on the in memory database and the still clock."""
    with session_client(session, still_clock) as client:
        production_app.dependency_overrides[get_notification_gateway] = lambda: email_gateway
        yield BookingClient(client, still_clock)


@pytest.fixture
def home_branch(session: Session, factory: Factory) -> Branch:
    """Return the committed branch a customer registers at, which is CBD."""
    branch = factory.branch(code=HOME_BRANCH_CODE)
    session.commit()
    return branch


@pytest.fixture
def account_api(
    session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
) -> Iterator[TestClient]:
    """Yield the account and profile routes, sending through the fake gateway of the test."""
    with account_client(session, still_clock, email_gateway) as client:
        yield client
