"""What a deployed service exposes, and what it says about itself.

Two things change between my machine and a deployed environment.

The interactive documentation and the OpenAPI document are served in
development and test and nowhere else. In staging and production the three
paths answer 404 like any other path that does not exist, as a problem
document, so the service does not confirm they were ever there.

The health endpoint names the revision that answered. Cloud Run sets
`K_REVISION` on every instance, and away from Cloud Run the endpoint says
`local`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.config import LOCAL_REVISION, Environment, settings
from tests.support.http import problem_code

HEALTH_PATH: Final[str] = "/api/health"
DOCUMENTATION_PATHS: Final[list[str]] = ["/docs", "/redoc", "/openapi.json"]
RELAXED_ENVIRONMENTS: Final[list[Environment]] = [Environment.DEVELOPMENT, Environment.TEST]
DEPLOYED_ENVIRONMENTS: Final[list[Environment]] = [Environment.STAGING, Environment.PRODUCTION]
HTTP_ERROR_PROBLEM: Final[str] = "http-error"
CLOUD_RUN_REVISION: Final[str] = "toolshed-hire-api-00042-xuv"
EXISTING_HEALTH_FIELDS: Final[set[str]] = {
    "status",
    "environment",
    "databaseReachable",
    "btreeGistInstalled",
}

ClientFactory = Callable[[Environment], TestClient]


class TestTheApiDocumentation:
    """Served where I develop, absent where the service is deployed."""

    @pytest.mark.parametrize("environment", RELAXED_ENVIRONMENTS)
    @pytest.mark.parametrize("path", DOCUMENTATION_PATHS)
    def test_development_and_test_serve_it(
        self, client_for_environment: ClientFactory, environment: Environment, path: str
    ) -> None:
        response = client_for_environment(environment).get(path)
        assert response.status_code == status.HTTP_200_OK

    def test_the_openapi_document_describes_the_api(
        self, client_for_environment: ClientFactory
    ) -> None:
        document = client_for_environment(Environment.TEST).get("/openapi.json").json()
        assert HEALTH_PATH in document["paths"]

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    @pytest.mark.parametrize("path", DOCUMENTATION_PATHS)
    def test_staging_and_production_answer_404_with_a_problem_document(
        self, client_for_environment: ClientFactory, environment: Environment, path: str
    ) -> None:
        response = client_for_environment(environment).get(path)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == HTTP_ERROR_PROBLEM

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_a_deployed_application_still_serves_its_api(
        self, client_for_environment: ClientFactory, environment: Environment
    ) -> None:
        response = client_for_environment(environment).get("/api/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTheHealthRevision:
    """`revision` says which Cloud Run revision answered, and `local` otherwise."""

    def test_the_revision_is_local_when_cloud_run_did_not_set_one(
        self, client: TestClient
    ) -> None:
        body = client.get(HEALTH_PATH).json()
        assert body["revision"] == LOCAL_REVISION == "local"

    def test_the_revision_is_the_one_cloud_run_named(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "revision", CLOUD_RUN_REVISION)
        body = client.get(HEALTH_PATH).json()
        assert body["revision"] == CLOUD_RUN_REVISION

    def test_the_fields_the_frontend_reads_are_still_there_under_the_same_names(
        self, client: TestClient
    ) -> None:
        body = client.get(HEALTH_PATH).json()
        assert body.keys() == EXISTING_HEALTH_FIELDS | {"revision"}
        assert body["environment"] == settings.environment.value
        assert body["databaseReachable"] is True
        # The in memory database has no btree_gist, which the report says plainly.
        assert body["btreeGistInstalled"] is False
        assert body["status"] == "degraded"
