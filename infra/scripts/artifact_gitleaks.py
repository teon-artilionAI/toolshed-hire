"""The directory gitleaks component of the pipeline artifact scan."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

from artifact_findings import Finding

GITLEAKS_CONFIG: Final[Path] = Path(__file__).resolve().parents[2] / ".gitleaks.toml"


def gitleaks_findings(paths: Iterable[Path], binary: Sequence[str]) -> list[Finding]:
    """Run the directory gitleaks scan over the artifact paths."""
    findings: list[Finding] = []
    for path in paths:
        if not path.exists():
            continue
        completed = subprocess.run(
            [
                *binary,
                "dir",
                str(path),
                "--config",
                str(GITLEAKS_CONFIG),
                "--no-banner",
                "--redact",
                "--exit-code",
                "1",
                "--report-format",
                "json",
                "--report-path",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            continue
        if completed.returncode != 1:
            findings.append(
                Finding(
                    str(path),
                    0,
                    "gitleaks-error",
                    f"gitleaks exited with code {completed.returncode}",
                )
            )
            continue
        try:
            report = json.loads(completed.stdout or "[]")
        except json.JSONDecodeError:
            findings.append(
                Finding(str(path), 0, "gitleaks-error", "gitleaks returned an unreadable report")
            )
            continue
        if not isinstance(report, list) or not report:
            findings.append(
                Finding(str(path), 0, "gitleaks-error", "gitleaks failed without a finding")
            )
            continue
        for item in report:
            findings.append(
                Finding(
                    str(item.get("File", path)),
                    int(item.get("StartLine", 0)),
                    "gitleaks",
                    "<redacted>",
                )
            )
    return findings
