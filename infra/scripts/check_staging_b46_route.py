#!/usr/bin/env python3
"""Fail if the B4.6 staging drill route can reach a deployment step.

This is a guard, not the drill. It checks the two workflow files that make the
no-deploy route possible:

- the drill workflow is triggered only by the request file on develop;
- the staging deployment workflow ignores that same request file;
- the drill has no job dependencies, deployment actions, deployment scripts,
  write permissions, extra secrets or extra repository variables;
- the drill runs only the existing B4.6 staging spec.

Run it from the repository root. ``--drill`` and ``--deploy`` exist so the
guard itself can be exercised against temporary negative fixtures.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DRILL = REPOSITORY_ROOT / ".github" / "workflows" / "staging-b46-network-loss.yml"
DEFAULT_DEPLOY = REPOSITORY_ROOT / ".github" / "workflows" / "deploy-staging.yml"
TRIGGER_PATH = ".github/b46-drill/trigger.json"
ALLOWED_USES = (
    "actions/checkout@",
    "actions/setup-node@",
    "actions/upload-artifact@",
)
ALLOWED_SECRETS = {"E2E_CUSTOMER_PASSWORD", "E2E_STAFF_PASSWORD"}
ALLOWED_VARIABLES = {"FRONTEND_ORIGIN"}
ALLOWED_SCRIPTS = {"check_staging_b46_route.py", "scan_artifacts.py"}
FORBIDDEN_RUN_TOKENS = (
    "deploy-api.sh",
    "deploy-frontend.sh",
    "build-and-push-image.sh",
    "apply-migrations.sh",
    "seed-database.sh",
    "promote-api.sh",
    "smoke-test.sh",
    "gcloud",
    "vercel",
    "alembic",
    "seed.py",
    "docker",
    "kubectl",
    "terraform",
    "psql",
    "gh workflow run",
    "git push",
    "npm run deploy",
    "wrangler",
    "flyctl",
)
FORBIDDEN_TRIGGERS = (
    "workflow_dispatch:",
    "pull_request:",
    "pull_request_target:",
    "schedule:",
    "workflow_run:",
    "repository_dispatch:",
    "release:",
    "workflow_call:",
)


def without_comments(text: str) -> str:
    """Drop whole-line comments so prose about deployment is not a command."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def indented_entries(text: str, key: str) -> list[str] | None:
    """Return the list entries directly under the first matching YAML key."""
    match = re.search(rf"(?ms)^(\s*){re.escape(key)}:\s*\n((?:\s+-\s+\S+\s*\n?)+)", text)
    if match is None:
        return None
    block = match.group(2)
    return [
        entry.strip()
        for entry in re.findall(r"^\s*-\s+(\S+)\s*$", block, flags=re.MULTILINE)
    ]


def run_blocks(text: str) -> list[str]:
    """Collect the value of every run: key, including its indented block."""
    lines = text.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*(.*)$", lines[index])
        if match is None:
            index += 1
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        block = [] if inline in ("", "|", ">") else [inline]
        index += 1
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                block.append("")
                index += 1
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= indent:
                break
            block.append(line.strip())
            index += 1
        blocks.append("\n".join(block))
    return blocks


def check_drill(text: str) -> list[str]:
    errors: list[str] = []
    plain = without_comments(text)

    for trigger in FORBIDDEN_TRIGGERS:
        if trigger in plain:
            errors.append(f"drill has a forbidden trigger: {trigger.rstrip(':')}")

    if not re.search(r"(?m)^on:\s*$", plain):
        errors.append("drill has no explicit on: block")
    branches = indented_entries(plain, "branches")
    if branches != ["develop"]:
        errors.append(f"drill branches must be exactly develop, found {branches!r}")
    paths = indented_entries(plain, "paths")
    if paths != [TRIGGER_PATH]:
        errors.append(f"drill paths must be exactly {TRIGGER_PATH}, found {paths!r}")
    if "paths-ignore:" in plain:
        errors.append("drill must use paths, not paths-ignore")

    if not re.search(
        r"(?ms)^concurrency:\s*\n\s+group:\s*deploy-staging\s*\n\s+cancel-in-progress:\s*false\s*$",
        plain,
    ):
        errors.append("drill must share the deploy-staging concurrency group without cancelling")

    if not re.search(r"(?m)^permissions:\s*$", plain):
        errors.append("drill has no permissions block")
    if not re.search(r"(?m)^\s+contents:\s*read\s*$", plain):
        errors.append("drill must grant contents: read")
    if re.search(r"(?m)^\s+[a-z-]+:\s*write\s*$", plain):
        errors.append("drill must not grant any write permission")

    if re.search(r"(?m)^\s+needs:", plain):
        errors.append("drill must not depend on another job")
    if re.search(r"(?m)^  deploy:\s*$", plain):
        errors.append("drill must not define a deploy job")
    if "github.ref == 'refs/heads/develop'" not in plain:
        errors.append("drill must run only on the develop ref")
    if not re.search(r"(?m)^\s+environment:\s*$", plain):
        errors.append("drill has no environment block")
    if not re.search(r"(?m)^\s+name:\s*staging\s*$", plain):
        errors.append("drill environment must be staging")

    for match in re.finditer(r"(?m)^\s+uses:\s*(\S+)", plain):
        use = match.group(1).strip("'\"")
        if not use.startswith(ALLOWED_USES):
            errors.append(f"drill uses an action outside the allowlist: {use}")

    for match in re.finditer(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}\}", plain):
        if match.group(1) not in ALLOWED_SECRETS:
            errors.append(f"drill reads an extra secret: {match.group(1)}")
    for match in re.finditer(r"\$\{\{\s*vars\.([A-Za-z0-9_]+)\s*\}\}", plain):
        if match.group(1) not in ALLOWED_VARIABLES:
            errors.append(f"drill reads an extra variable: {match.group(1)}")

    for match in re.finditer(r"infra/scripts/([A-Za-z0-9_.-]+)", plain):
        if match.group(1) not in ALLOWED_SCRIPTS:
            errors.append(f"drill reaches an extra script: {match.group(1)}")

    for block in run_blocks(plain):
        for token in FORBIDDEN_RUN_TOKENS:
            if token in block:
                errors.append(f"drill run block contains a deployment token: {token}")

    if "npx playwright test --project=staging e2e/b46-network-loss.spec.ts" not in plain:
        errors.append("drill does not run the existing B4.6 staging spec")
    if "/api/health" not in plain:
        errors.append("drill does not read the staging health endpoint")
    if "expected_revision" not in plain or "expected_sha" not in plain:
        errors.append("drill does not verify the requested staging revision and SHA")

    return errors


def check_deploy(text: str) -> list[str]:
    errors: list[str] = []
    plain = without_comments(text)
    branches = indented_entries(plain, "branches")
    if branches != ["develop"]:
        errors.append(f"deploy branches must be exactly develop, found {branches!r}")
    ignored = indented_entries(plain, "paths-ignore")
    if ignored != [TRIGGER_PATH]:
        errors.append(
            f"deploy paths-ignore must be exactly {TRIGGER_PATH}, found {ignored!r}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drill", type=Path, default=DEFAULT_DRILL)
    parser.add_argument("--deploy", type=Path, default=DEFAULT_DEPLOY)
    args = parser.parse_args()

    errors: list[str] = []
    for path in (args.drill, args.deploy):
        if not path.is_file():
            errors.append(f"missing workflow file: {path}")
    if errors:
        for error in errors:
            print(f"::error title=B4.6 no-deploy guard::{error}")
        return 1

    errors.extend(check_drill(args.drill.read_text(encoding="utf-8")))
    errors.extend(check_deploy(args.deploy.read_text(encoding="utf-8")))
    if errors:
        for error in errors:
            print(f"::error title=B4.6 no-deploy guard::{error}")
        return 1

    print(f"B4.6 no-deploy guard passed for {args.drill} and {args.deploy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
