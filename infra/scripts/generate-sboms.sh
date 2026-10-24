#!/usr/bin/env bash
#
# Generate the CycloneDX bills of materials for the release.
#
# The backend SBOM is read from the hashed runtime requirements, so it lists the
# packages the image installs and not the test tools. The frontend SBOM is read
# from package-lock.json. Both are validated before they are written.
#
# Usage:
#   bash infra/scripts/generate-sboms.sh [output-directory]
#
# The default output directory is ./sbom in the repository root.

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${1:-${REPOSITORY_ROOT}/sbom}"
PYTHON="${PYTHON:-python3}"
PYTHON_TOOL_VERSION="7.5.0"
NPM_TOOL_VERSION="6.0.1"

mkdir -p "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"

tmp_root="${RUNNER_TEMP:-$(mktemp -d)}"
venv="${tmp_root}/toolshed-sbom-venv"
rm -rf "${venv}"
"${PYTHON}" -m venv "${venv}"
"${venv}/bin/pip" install --quiet --disable-pip-version-check "cyclonedx-bom==${PYTHON_TOOL_VERSION}"

echo "Generating the backend SBOM from backend/requirements.txt."
"${venv}/bin/cyclonedx-py" requirements \
  "${REPOSITORY_ROOT}/backend/requirements.txt" \
  --pyproject "${REPOSITORY_ROOT}/backend/pyproject.toml" \
  --output-reproducible \
  --validate \
  --output-file "${OUTPUT_DIR}/sbom-backend.cdx.json"

echo "Generating the frontend SBOM from frontend/package-lock.json."
cd "${REPOSITORY_ROOT}/frontend"
# npm ls reports the optional WASI wasm packages as missing on some platforms
# even when npm ci succeeded. The lock file is the source of truth here, and
# --validate still rejects a malformed BOM.
npx --yes "@cyclonedx/cyclonedx-npm@${NPM_TOOL_VERSION}" \
  --package-lock-only \
  --ignore-npm-errors \
  --output-reproducible \
  --validate \
  --output-format JSON \
  --output-file "${OUTPUT_DIR}/sbom-frontend.cdx.json"

python3 - "${OUTPUT_DIR}" <<'PYTHON'
import json
import sys
from pathlib import Path

output = Path(sys.argv[1])
for name in ("sbom-backend.cdx.json", "sbom-frontend.cdx.json"):
    path = output / name
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"{name} was not written")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("bomFormat") != "CycloneDX":
        raise SystemExit(f"{name} is not a CycloneDX document")
    print(f"{name}: {len(data.get('components', []))} components")
PYTHON
