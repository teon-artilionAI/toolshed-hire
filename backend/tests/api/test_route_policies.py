"""Deny by default: the route table, the start-up refusal and the role matrix.

Three things are pinned here (BR-41, C-20, C-21, C-25).

Every route of the real application declares who may call it, and this test
enumerates the route table to say so. A route added without a policy fails
here, in the build, before it can fail a deployment. The policy expected of
each route is listed in tests/api/route_policy_expectations.py.

An application with one undeclared route refuses to start, and the message
names the route.

And one table says, for a representative endpoint of every module and for the
three roles and an anonymous caller, exactly who is let in and who is answered
401 or 403. The table is `MATRIX` in tests/api/role_matrix.py, and a later
change adds a row to it and nothing else.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.access_policy import (
    UndeclaredPolicyError,
    declared_routes,
    enforce_declared_policies,
)
from app.api.deps import AdminUser, public_access
from app.config import Environment
from app.domain.enums import UserRole
from app.main import FRAMEWORK_ROUTE_PATHS, create_app
from app.main import app as production_app
from tests.api.role_matrix import API, MATRIX, Caller, MatrixRow
from tests.api.route_policy_expectations import EXPECTED_POLICIES
from tests.support.factories import Factory
from tests.support.tokens import authorization_header, mint_access_token

REFUSALS: Final[frozenset[int]] = frozenset(
    {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
)
UNDECLARED_PATH: Final[str] = "/api/left-open-by-mistake"
CONTRADICTORY_PATH: Final[str] = "/api/public-and-admin-at-once"

CELLS: Final[list[tuple[MatrixRow, Caller]]] = [
    (row, caller) for row in MATRIX for caller in Caller
]


class TestTheRouteTable:
    """Every route says who may call it, and says what this file expects."""

    def test_every_route_of_the_real_application_declares_a_policy(self) -> None:
        routes = declared_routes(production_app, framework_paths=FRAMEWORK_ROUTE_PATHS)
        undeclared = [route.name for route in routes if not route.policies]
        assert routes, "The route table is empty, so the check above checked nothing."
        assert undeclared == [], (
            f"These routes declare no policy: {undeclared}. Give each a role dependency, or "
            "`public_access` when it admits a caller with no account (BR-41)."
        )

    def test_each_api_route_declares_exactly_the_policy_expected_of_it(self) -> None:
        declared = {
            route.name: {(policy.kind, policy.roles) for policy in route.policies}
            for route in declared_routes(production_app, framework_paths=FRAMEWORK_ROUTE_PATHS)
            if route.path not in FRAMEWORK_ROUTE_PATHS
        }
        assert declared == {name: {policy} for name, policy in EXPECTED_POLICIES.items()}

    def test_the_documentation_routes_are_the_only_ones_without_a_dependency_tree(self) -> None:
        bare = {
            context.path
            for context in iter_route_contexts(production_app.routes)
            if not isinstance(context.original_route, APIRoute)
        }
        assert bare == FRAMEWORK_ROUTE_PATHS

    @pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
    def test_a_deployed_application_passes_with_no_exception_made_for_any_path(
        self, applications_by_environment: dict[Environment, FastAPI], environment: Environment
    ) -> None:
        application = applications_by_environment[environment]
        enforce_declared_policies(application)
        assert all(route.policies for route in declared_routes(application))

    def test_the_matrix_has_a_row_for_every_module_that_has_a_router(self) -> None:
        tags = {
            str(tag)
            for context in iter_route_contexts(production_app.routes)
            if isinstance(context.original_route, APIRoute)
            for tag in context.tags
        }
        assert {row.module for row in MATRIX if row.application == API} == tags


@pytest.fixture(scope="module")
def application_with_an_undeclared_route() -> FastAPI:
    """Return the real application with one route added that declares nothing.

    Built once and up front, for the reason the fixtures in conftest.py give.
    """
    application = create_app()

    @application.get(UNDECLARED_PATH)
    def left_open() -> dict[str, str]:
        """Answer anybody, because nobody declared who may ask."""
        return {"status": "open"}

    return application


class TestTheStartUpRefusal:
    """An application with an undeclared route does not start (C-21)."""

    def test_an_application_with_one_undeclared_route_refuses_to_start(
        self, application_with_an_undeclared_route: FastAPI
    ) -> None:
        with (
            pytest.raises(UndeclaredPolicyError) as refusal,
            TestClient(application_with_an_undeclared_route),
        ):
            pytest.fail("The application started with a route that declares no policy.")
        assert f"GET {UNDECLARED_PATH}" in str(refusal.value)
        assert "Refusing to start" in str(refusal.value)

    def test_the_check_names_only_the_route_that_is_at_fault(self) -> None:
        application = FastAPI()

        @application.get("/declared", dependencies=[Depends(public_access)])
        def declared() -> None:
            """Declare that anybody may ask."""

        @application.get(UNDECLARED_PATH)
        def left_open() -> None:
            """Declare nothing."""

        with pytest.raises(UndeclaredPolicyError) as refusal:
            enforce_declared_policies(application, framework_paths=FRAMEWORK_ROUTE_PATHS)
        assert f"['GET {UNDECLARED_PATH}']" in str(refusal.value)
        assert "/declared" not in str(refusal.value)

    def test_a_route_that_is_public_and_protected_at_once_is_refused(self) -> None:
        application = FastAPI()

        @application.get(CONTRADICTORY_PATH, dependencies=[Depends(public_access)])
        def confused(user: AdminUser) -> None:
            """Declare that anybody may ask, and that only an administrator may."""

        with pytest.raises(UndeclaredPolicyError, match=CONTRADICTORY_PATH):
            enforce_declared_policies(application)

    def test_a_route_the_framework_did_not_declare_is_refused_too(self) -> None:
        application = FastAPI()
        with pytest.raises(UndeclaredPolicyError, match="/openapi.json"):
            enforce_declared_policies(application)


@pytest.fixture
def credentials(session: Session, factory: Factory) -> dict[Caller, dict[str, str]]:
    """Return the request headers of each kind of caller, the anonymous one included."""
    accounts = {
        Caller.CUSTOMER: factory.user(role=UserRole.CUSTOMER),
        Caller.COUNTER: factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch()),
        Caller.ADMIN: factory.user(role=UserRole.ADMIN),
    }
    session.commit()
    headers = {
        caller: authorization_header(mint_access_token(account.id, role=account.role))
        for caller, account in accounts.items()
    }
    return {Caller.ANONYMOUS: {}, **headers}


class TestTheRoleAndEndpointMatrix:
    """One endpoint of every module, three roles and nobody (C-25)."""

    @pytest.mark.parametrize(
        ("row", "caller"), CELLS, ids=[f"{row.module}/{caller.value}" for row, caller in CELLS]
    )
    def test_the_caller_is_let_in_or_refused_exactly_as_the_table_says(
        self,
        client: TestClient,
        probe_client: TestClient,
        credentials: dict[Caller, dict[str, str]],
        row: MatrixRow,
        caller: Caller,
    ) -> None:
        chosen = client if row.application == API else probe_client
        response = chosen.request(row.method, row.path, headers=credentials[caller])
        if caller in row.admits:
            assert response.status_code not in REFUSALS, (
                f"{row.method} {row.path} refused a {caller.value} caller with "
                f"{response.status_code}, and the table says it lets them in."
            )
        elif caller is Caller.ANONYMOUS:
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        else:
            assert response.status_code == status.HTTP_403_FORBIDDEN
