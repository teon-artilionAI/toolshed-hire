"""The artifact publication boundary and the release asset repository context.

A green scan that still uploads its artifact is not a publication gate. These
checks read the actual workflow files, so a future edit cannot quietly detach
an upload from its scan or drop the gitleaks component.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"
PINNED_CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"


def workflow_documents() -> list[tuple[Path, dict]]:
    """Return every parsed workflow file."""
    documents: list[tuple[Path, dict]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        documents.append((path, yaml.safe_load(path.read_text(encoding="utf-8"))))
    return documents


def test_every_artifact_upload_depends_on_a_successful_scan() -> None:
    """An upload must follow the scanner and require its success."""
    for path, document in workflow_documents():
        for job_name, job in (document.get("jobs") or {}).items():
            scan_id: str | None = None
            install_seen = False
            for step in job.get("steps") or []:
                run = step.get("run", "")
                if "install-gitleaks.sh" in run:
                    install_seen = True
                if "scan_artifacts.py" in run:
                    assert install_seen, f"{path.name}:{job_name}: scan before gitleaks install"
                    assert "--gitleaks" in run, f"{path.name}:{job_name}: scan without gitleaks"
                    scan_id = step.get("id")
                    assert scan_id, f"{path.name}:{job_name}: scan has no id"
                uses = step.get("uses", "")
                if uses.startswith("actions/upload-artifact@"):
                    assert scan_id, f"{path.name}:{job_name}: upload has no preceding scan"
                    condition = step.get("if", "")
                    assert f"steps.{scan_id}.outcome == 'success'" in condition, (
                        f"{path.name}:{job_name}: upload must require steps.{scan_id}.outcome"
                    )


def test_release_assets_have_repository_context_and_a_scan() -> None:
    """The production release-assets job is explicit about its repository."""
    path = WORKFLOWS / "deploy-production.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    job = document["jobs"]["release-assets"]
    steps = job["steps"]
    gh_commands = [step for step in steps if "gh " in step.get("run", "")]
    assert gh_commands, "release-assets has no gh commands"
    for step in gh_commands:
        assert '--repo "${GITHUB_REPOSITORY}"' in step["run"], (
            f"release-assets command lacks --repo: {step.get('name')}"
        )
    scan = next(step for step in steps if "scan_artifacts.py" in step.get("run", ""))
    assert "--gitleaks" in scan["run"]
    assert scan.get("id") == "release_scan"
    for step in steps:
        name = step.get("name", "")
        if name == "Create a draft Release if it does not exist" or name == "Upload the two SBOMs":
            assert "steps.release_scan.outcome == 'success'" in step.get("if", "")


def test_release_assets_check_out_the_release_revision_before_local_helpers() -> None:
    """The release job can read its own scripts before installing or scanning."""
    path = WORKFLOWS / "deploy-production.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = document["jobs"]["release-assets"]["steps"]
    checkout_index = next(
        index for index, step in enumerate(steps) if step.get("uses") == PINNED_CHECKOUT
    )
    checkout = steps[checkout_index]
    assert checkout.get("with", {}).get("ref") == "${{ github.sha }}"
    install_index = next(
        index
        for index, step in enumerate(steps)
        if "install-gitleaks.sh" in step.get("run", "")
    )
    scan_index = next(
        index for index, step in enumerate(steps) if "scan_artifacts.py" in step.get("run", "")
    )
    assert checkout_index < install_index < scan_index, (
        "release-assets must check out the release revision before both local helpers"
    )
