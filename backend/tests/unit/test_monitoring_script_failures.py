"""Discovery failures and policy replacement safety in the monitoring scripts.

The tests run the real shell scripts with a fake gcloud on PATH. The fake
records every call and can return 77 for a chosen discovery path. A denied or
unavailable discovery must stop before any write, and a policy replacement must
create the new policy before deleting the old one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UPTIME = REPOSITORY_ROOT / "infra" / "scripts" / "create-uptime-checks.sh"
ALERTS = REPOSITORY_ROOT / "infra" / "scripts" / "create-alert-policies.sh"

FAKE_GCLOUD = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GCLOUD_CALLS"
mode="${GCLOUD_MODE:-existing}"
case "$1 $2 $3" in
  "beta monitoring channels list")
    [ "$mode" = discovery-fail ] && exit 77
    echo 'projects/toolshed-hire/notificationChannels/1'
    ;;
  "beta monitoring channels create") echo 'projects/toolshed-hire/notificationChannels/2' ;;
  "logging metrics describe")
    [ "$mode" = metric-discovery-fail ] && exit 77
    [ "$mode" = absent ] && { echo 'NOT_FOUND' >&2; exit 1; }
    echo 'metric exists'
    ;;
  "logging metrics create")
    [ "$mode" = create-fail ] && exit 77
    echo 'metric created'
    ;;
  "monitoring policies list")
    [ "$mode" = policy-discovery-fail ] && exit 77
    [ "$mode" = absent ] && exit 0
    echo 'projects/toolshed-hire/alertPolicies/1'
    ;;
  "monitoring policies create")
    [ "$mode" = policy-create-fail ] && exit 77
    echo 'policy created'
    ;;
  "monitoring policies delete")
    [ "$mode" = policy-delete-fail ] && exit 77
    echo 'policy deleted'
    ;;
  "monitoring uptime list-configs")
    [ "$mode" = discovery-fail ] && exit 77
    [ "$mode" = absent ] && exit 0
    echo 'Toolshed Hire liveness (toolshed-hire-staging.vercel.app)'
    ;;
  "monitoring uptime create") echo 'uptime created' ;;
  "scheduler jobs describe")
    [ "$mode" = discovery-fail ] && exit 77
    [ "$mode" = absent ] && { echo 'NOT_FOUND' >&2; exit 1; }
    echo 'state: ENABLED'
    ;;
  "scheduler jobs create") echo 'job created' ;;
  "scheduler jobs update") echo 'job updated' ;;
  *) echo "unexpected gcloud call: $*" >&2; exit 99 ;;
esac
"""


@pytest.fixture
def fake_gcloud(tmp_path: Path) -> tuple[Path, Path]:
    """Return the stub directory and the call log."""
    binary = tmp_path / "gcloud"
    binary.write_text(FAKE_GCLOUD, encoding="utf-8")
    binary.chmod(0o755)
    return tmp_path, tmp_path / "calls.log"


def run_script(
    script: Path, stub: Path, calls: Path, mode: str, *, replace: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run one script with the stub first on PATH."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{stub}{os.pathsep}{env['PATH']}",
            "GCLOUD_CALLS": str(calls),
            "GCLOUD_MODE": mode,
            "GCLOUD_CONFIGURATION": "toolshed",
            "UPTIME_HOST": "toolshed-hire-staging.vercel.app",
            "GCP_PROJECT": "toolshed-hire",
            "PROJECT": "toolshed-hire",
            "OWNER": "teon@sulako.com",
            "REPLACE_EXISTING": "1" if replace else "0",
        }
    )
    return subprocess.run(
        [bash, str(script)], env=env, capture_output=True, text=True, check=False
    )


def called(calls: Path) -> list[str]:
    """Return the logged calls, or an empty list."""
    return calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


@pytest.mark.skipif(sys.platform == "win32", reason="The fake gcloud is POSIX bash.")
class TestUptimeDiscovery:
    """Discovery failures stop before any uptime or scheduler write."""

    def test_a_failed_liveness_list_stops_before_create(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(UPTIME, stub, calls, "discovery-fail")
        log = called(calls)
        assert result.returncode != 0
        assert any("uptime list-configs" in line for line in log)
        assert not any("uptime create" in line for line in log)
        assert not any("scheduler jobs" in line for line in log)

    def test_a_failed_scheduler_read_stops_before_create(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(UPTIME, stub, calls, "discovery-fail")
        assert result.returncode != 0
        assert not any("scheduler jobs create" in line for line in called(calls))

    def test_confirmed_absence_creates_the_liveness_and_job(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(UPTIME, stub, calls, "absent")
        log = called(calls)
        assert result.returncode == 0, result.stderr
        assert any("uptime create" in line for line in log)
        assert any("scheduler jobs create" in line for line in log)

    def test_existing_resources_do_not_create(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(UPTIME, stub, calls, "existing")
        log = called(calls)
        assert result.returncode == 0, result.stderr
        assert not any("uptime create" in line for line in log)
        assert any("scheduler jobs update" in line for line in log)
        assert not any("scheduler jobs create" in line for line in log)


@pytest.mark.skipif(sys.platform == "win32", reason="The fake gcloud is POSIX bash.")
class TestAlertDiscoveryAndReplacement:
    """Discovery failures stop before writes and replacement is create-first."""

    def test_a_failed_channel_list_stops_before_any_write(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(ALERTS, stub, calls, "discovery-fail")
        log = called(calls)
        assert result.returncode != 0
        assert not any("metrics create" in line for line in log)
        assert not any("policies create" in line for line in log)
        assert not any("policies delete" in line for line in log)

    def test_a_failed_metric_read_stops_before_metric_create(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(ALERTS, stub, calls, "metric-discovery-fail")
        log = called(calls)
        assert result.returncode != 0
        assert not any("metrics create" in line for line in log)
        assert not any("policies create" in line for line in log)

    def test_a_failed_policy_read_stops_before_policy_write(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(ALERTS, stub, calls, "policy-discovery-fail")
        log = called(calls)
        assert result.returncode != 0
        assert not any("policies create" in line for line in log)
        assert not any("policies delete" in line for line in log)

    def test_replacement_creates_before_deleting(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(ALERTS, stub, calls, "existing", replace=True)
        log = called(calls)
        assert result.returncode == 0, result.stderr
        first_create = next(i for i, line in enumerate(log) if "policies create" in line)
        first_delete = next(i for i, line in enumerate(log) if "policies delete" in line)
        assert first_create < first_delete

    def test_a_failed_replacement_create_keeps_the_old_policy(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(ALERTS, stub, calls, "policy-create-fail", replace=True)
        log = called(calls)
        assert result.returncode != 0
        assert any("policies create" in line for line in log)
        assert not any("policies delete" in line for line in log)

    def test_a_failed_delete_after_create_names_the_duplicate(self, fake_gcloud) -> None:
        stub, calls = fake_gcloud
        result = run_script(ALERTS, stub, calls, "policy-delete-fail", replace=True)
        log = called(calls)
        assert result.returncode != 0
        assert any("policies create" in line for line in log)
        assert any("policies delete" in line for line in log)
        assert "Old policy still present" in result.stderr
