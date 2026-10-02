"""The attributes of the refresh cookie, and the `Origin` check on the cookie routes (C-19).

The cookie is `HttpOnly`, `Secure`, `SameSite=Strict` and scoped to
`/api/auth`. `Secure` is dropped in development and test and nowhere else, so
the application each environment would run is asked for its cookie and the
header is compared whole.

The two routes a cookie authenticates check where the request came from. An
`Origin` that is not one of the configured `CORS_ORIGINS` is 403. No `Origin`
at all is allowed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.refresh_cookie import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH, RefreshCookie
from app.config import Environment
from app.domain.enums import RevokeReason, UserRole
from app.domain.session import REFRESH_IDLE_LIFETIME
from app.infrastructure.models import RefreshSession, UserAccount
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.request_probe import build_request_probe_app, settings_for
from tests.support.sessions import (
    ALLOWED_ORIGIN,
    FOREIGN_ORIGIN,
    LOGOUT_PATH,
    ORIGIN_NOT_ALLOWED_PROBLEM,
    REFRESH_PATH,
    present,
    refresh_cookie_header,
    refresh_token_of,
    session_client,
    sign_in,
)

IDLE_SECONDS: Final[int] = int(REFRESH_IDLE_LIFETIME.total_seconds())
FAKE_TOKEN: Final[str] = "made-up-refresh-token-for-this-test"
SECURE_ENVIRONMENTS: Final[list[Environment]] = [Environment.STAGING, Environment.PRODUCTION]
PLAIN_HTTP_ENVIRONMENTS: Final[list[Environment]] = [Environment.DEVELOPMENT, Environment.TEST]
COOKIE_ROUTES: Final[list[str]] = [REFRESH_PATH, LOGOUT_PATH]
PUBLIC_SITE_ORIGIN: Final[str] = "https://www.toolshedhire.example"


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = factory.user(role=UserRole.CUSTOMER)
    session.commit()
    return account


@pytest.fixture
def client_in(
    session: Session, applications_by_environment: dict[Environment, FastAPI]
) -> Iterator[dict[Environment, TestClient]]:
    """Yield a client for the application each environment would run, on one session."""
    clients: dict[Environment, TestClient] = {}
    managers = []
    for environment, application in applications_by_environment.items():
        manager = session_client(session, application=application)
        clients[environment] = manager.__enter__()
        managers.append(manager)
    try:
        yield clients
    finally:
        for manager in reversed(managers):
            manager.__exit__(None, None, None)


@pytest.fixture(scope="module")
def two_origin_app() -> FastAPI:
    """Return the application a deployment with two configured origins would run.

    Built once and up front, for the reason the fixtures in conftest.py give.
    """
    return build_request_probe_app(
        settings_for(Environment.TEST, CORS_ORIGINS=f"{PUBLIC_SITE_ORIGIN}, {ALLOWED_ORIGIN}")
    )


class TestTheCookieAttributes:
    """`HttpOnly; Secure; SameSite=Strict; Path=/api/auth`, compared whole."""

    def test_the_name_and_the_path_are_the_documented_ones(self) -> None:
        assert REFRESH_COOKIE_NAME == "toolshed_refresh"
        assert REFRESH_COOKIE_PATH == "/api/auth"

    def test_the_header_written_for_https_is_exactly_this(self) -> None:
        header = RefreshCookie(secure=True).header_value(FAKE_TOKEN, IDLE_SECONDS)
        assert header == (
            f"toolshed_refresh={FAKE_TOKEN}; Max-Age=604800; Path=/api/auth; "
            "HttpOnly; Secure; SameSite=Strict"
        )

    def test_the_header_that_clears_it_carries_the_same_attributes(self) -> None:
        assert RefreshCookie(secure=True).clearing_header_value() == (
            "toolshed_refresh=; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; "
            "Path=/api/auth; HttpOnly; Secure; SameSite=Strict"
        )

    @pytest.mark.parametrize("environment", SECURE_ENVIRONMENTS)
    def test_staging_and_production_set_it_secure(
        self,
        client_in: dict[Environment, TestClient],
        customer: UserAccount,
        environment: Environment,
    ) -> None:
        response = sign_in(client_in[environment], customer.email)
        assert response.status_code == status.HTTP_200_OK
        token = refresh_token_of(response)
        assert refresh_cookie_header(response) == (
            f"toolshed_refresh={token}; Max-Age={IDLE_SECONDS}; Path=/api/auth; "
            "HttpOnly; Secure; SameSite=Strict"
        )

    @pytest.mark.parametrize("environment", PLAIN_HTTP_ENVIRONMENTS)
    def test_development_and_test_drop_secure_and_nothing_else(
        self,
        client_in: dict[Environment, TestClient],
        customer: UserAccount,
        environment: Environment,
    ) -> None:
        response = sign_in(client_in[environment], customer.email)
        token = refresh_token_of(response)
        assert refresh_cookie_header(response) == (
            f"toolshed_refresh={token}; Max-Age={IDLE_SECONDS}; Path=/api/auth; "
            "HttpOnly; SameSite=Strict"
        )

    def test_a_refresh_in_production_replaces_it_with_the_same_attributes(
        self, client_in: dict[Environment, TestClient], customer: UserAccount
    ) -> None:
        client = client_in[Environment.PRODUCTION]
        first = refresh_token_of(sign_in(client, customer.email))
        response = present(client, REFRESH_PATH, first)
        assert response.status_code == status.HTTP_200_OK
        header = refresh_cookie_header(response)
        assert header.endswith("; Path=/api/auth; HttpOnly; Secure; SameSite=Strict")
        assert refresh_token_of(response) != first

    def test_a_logout_in_production_clears_it_with_the_same_attributes(
        self, client_in: dict[Environment, TestClient], customer: UserAccount
    ) -> None:
        client = client_in[Environment.PRODUCTION]
        token = refresh_token_of(sign_in(client, customer.email))
        response = present(client, LOGOUT_PATH, token)
        assert refresh_cookie_header(response) == (
            "toolshed_refresh=; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; "
            "Path=/api/auth; HttpOnly; Secure; SameSite=Strict"
        )

    def test_the_cookie_is_scoped_so_the_client_sends_it_to_the_auth_routes_only(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        sign_in(auth_client, customer.email)
        (cookie,) = auth_client.cookies.jar
        assert cookie.path == REFRESH_COOKIE_PATH
        assert cookie.has_nonstandard_attr("HttpOnly")


class TestTheOriginCheck:
    """A cookie route refuses a request that names another site (C-19)."""

    @pytest.mark.parametrize("path", COOKIE_ROUTES)
    def test_a_foreign_origin_is_403(self, auth_client: TestClient, path: str) -> None:
        response = present(auth_client, path, FAKE_TOKEN, headers={"Origin": FOREIGN_ORIGIN})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == ORIGIN_NOT_ALLOWED_PROBLEM

    @pytest.mark.parametrize("origin", ["null", "http://localhost:5173.evil.example", ""])
    def test_an_origin_that_only_resembles_the_site_is_403(
        self, auth_client: TestClient, origin: str
    ) -> None:
        response = present(auth_client, REFRESH_PATH, FAKE_TOKEN, headers={"Origin": origin})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_a_foreign_origin_cannot_sign_somebody_out(
        self, auth_client: TestClient, session: Session, customer: UserAccount
    ) -> None:
        token = refresh_token_of(sign_in(auth_client, customer.email))
        present(auth_client, LOGOUT_PATH, token, headers={"Origin": FOREIGN_ORIGIN})
        (stored,) = session.exec(select(RefreshSession)).all()
        assert stored.revoked_at is None
        assert stored.revoked_reason is not RevokeReason.LOGOUT

    def test_a_configured_origin_is_let_through(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        token = refresh_token_of(sign_in(auth_client, customer.email))
        response = present(auth_client, REFRESH_PATH, token, headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == status.HTTP_200_OK

    def test_the_comparison_ignores_case_and_a_trailing_slash(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        token = refresh_token_of(sign_in(auth_client, customer.email))
        response = present(
            auth_client, LOGOUT_PATH, token, headers={"Origin": "HTTP://LOCALHOST:5173/"}
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    @pytest.mark.parametrize("path", COOKIE_ROUTES)
    def test_a_request_with_no_origin_is_allowed(self, auth_client: TestClient, path: str) -> None:
        response = present(auth_client, path, None)
        assert response.status_code != status.HTTP_403_FORBIDDEN

    def test_the_list_comes_from_cors_origins(
        self, session: Session, customer: UserAccount, two_origin_app: FastAPI
    ) -> None:
        with session_client(session, application=two_origin_app) as client:
            token = refresh_token_of(sign_in(client, customer.email))
            allowed = present(client, REFRESH_PATH, token, headers={"Origin": PUBLIC_SITE_ORIGIN})
            refused = present(client, REFRESH_PATH, token, headers={"Origin": FOREIGN_ORIGIN})
        assert allowed.status_code == status.HTTP_200_OK
        assert refused.status_code == status.HTTP_403_FORBIDDEN
