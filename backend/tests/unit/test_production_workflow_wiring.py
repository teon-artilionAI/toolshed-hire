"""The prepared production stage-3 workflow wiring (AUD-009).

The production workflow is not executed by this test. It checks the reviewed
source keeps the staging function/IAM path, authenticates the candidate smoke
test, restores the deployer, and asks the header check to prove a direct call
is refused.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "deploy-production.yml"


def deploy_job() -> dict:
    """Return the deploy job of the production workflow."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["deploy"]


def step(job: dict, name: str) -> dict:
    """Return one named step of a job."""
    return next(candidate for candidate in job["steps"] if candidate.get("name") == name)


def test_stage_three_uses_the_function_and_iam_path() -> None:
    """Production uses the same protected path staging proves."""
    env = deploy_job()["env"]
    assert env["API_ACCESS"] == "iam"
    assert env["API_ROUTE"] == "function"
    assert env["GCP_WORKLOAD_AUDIENCE"] == "${{ vars.GCP_WORKLOAD_AUDIENCE }}"
    assert env["GCP_INVOKER_ACCOUNT"] == "${{ vars.GCP_INVOKER_ACCOUNT }}"


def test_candidate_smoke_uses_an_id_token_and_the_headers_check_direct_refusal() -> None:
    """The candidate is authenticated and the service's own address is probed."""
    job = deploy_job()
    identity = step(job, "Get an ID token for the candidate smoke test")
    assert identity["with"]["token_format"] == "id_token"
    assert identity["with"]["id_token_audience"] == "${{ steps.api.outputs.service_url }}"
    smoke = step(job, "Smoke test the candidate revision")
    assert smoke["env"]["SMOKE_TEST_ID_TOKEN"] == "${{ steps.smoke_identity.outputs.id_token }}"
    headers = step(job, "Check the security headers and TLS of the deployed site")
    assert headers["env"]["IAM_ONLY_SERVICE_URL"] == "${{ steps.api.outputs.service_url }}"
    assert any(
        candidate.get("name") == "Restore the deployer identity"
        for candidate in job["steps"]
    )


def test_the_release_image_is_pushed_under_its_release_tag() -> None:
    """The build step sees the release tag, so the cleanup policy keeps the image (NFR-18)."""
    job = deploy_job()
    assert job["env"]["RELEASE_TAG"] == "${{ github.ref_name }}"
    build = step(job, "Build and push the image")
    assert "RELEASE_TAG" not in build.get("env", {})
    script = (WORKFLOW.parents[2] / "infra" / "scripts" / "build-and-push-image.sh").read_text(encoding="utf-8")
    assert 'docker push "${repository}:${RELEASE_TAG}"' in script
