"""The committed uptime recreation script (B3.1).

The script runs a fake gcloud on PATH, so the test proves the actual command
arguments without touching a cloud project. The real read-back remains an
authorized operational step.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "infra" / "scripts" / "create-uptime-checks.sh"


@pytest.mark.skipif(sys.platform == "win32", reason="The command stub runs under POSIX bash.")
def test_the_script_creates_the_liveness_and_hourly_scheduler_definitions(
    tmp_path: Path,
) -> None:
    """The generated arguments use minutes, valid regions and the hourly job."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    stub = tmp_path / "gcloud"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$GCLOUD_CALLS\"\n"
        "if [[ \"$1 $2 $3\" == \"monitoring uptime list-configs\" ]]; then\n"
        "  if [[ -f \"$GCLOUD_LIVE_MARKER\" ]]; then printf '%s\\n' \"$GCLOUD_LIVE_NAME\"; fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2 $3\" == \"monitoring uptime create\" ]]; then\n"
        "  touch \"$GCLOUD_LIVE_MARKER\"; exit 0; fi\n"
        "if [[ \"$1 $2 $3\" == \"scheduler jobs describe\" ]]; then\n"
        "  if [[ -f \"$GCLOUD_JOB_MARKER\" ]]; then echo 'state: ENABLED'; exit 0; fi\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"$1 $2 $3\" == \"scheduler jobs create\" ]]; then\n"
        "  touch \"$GCLOUD_JOB_MARKER\"; exit 0; fi\n"
        "if [[ \"$1 $2 $3\" == \"scheduler jobs update\" ]]; then exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    calls = tmp_path / "calls.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "GCLOUD_CALLS": str(calls),
            "GCLOUD_LIVE_MARKER": str(tmp_path / "live.marker"),
            "GCLOUD_JOB_MARKER": str(tmp_path / "job.marker"),
            "GCLOUD_LIVE_NAME": "Toolshed Hire liveness (toolshed-hire-staging.vercel.app)",
            "UPTIME_HOST": "toolshed-hire-staging.vercel.app",
            "GCP_PROJECT": "toolshed-hire",
            "GCLOUD_CONFIGURATION": "toolshed",
            "SCHEDULER_LOCATION": "europe-west2",
            "ENVIRONMENT_NAME": "staging",
        }
    )
    result = subprocess.run(
        [bash, str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    log = calls.read_text(encoding="utf-8")
    assert "monitoring uptime create Toolshed Hire liveness" in log
    assert "--period=5" in log
    assert "--regions=usa-iowa,europe,asia-pacific" in log
    assert "scheduler jobs create http toolshed-full-health-staging" in log
    assert "--schedule=0 * * * *" in log
    assert "--uri=https://toolshed-hire-staging.vercel.app/api/health" in log
    assert "--location=europe-west2" in log
    assert "europe-west1" not in log
