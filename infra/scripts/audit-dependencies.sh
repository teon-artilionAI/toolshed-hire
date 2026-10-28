#!/usr/bin/env bash
#
# Run the dependency audits in one place, so the pull request check and the
# weekly schedule cannot drift apart.
#
# The backend and frontend must already be installed. The calling workflow sets
# up Python and Node before this script runs.

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Installing the backend and its development dependencies for the audit."
cd "${REPOSITORY_ROOT}/backend"
python -m pip install --upgrade pip
pip install --require-hashes --requirement requirements-dev.txt
pip install --no-deps --no-build-isolation --editable .

echo "Auditing Python dependencies."
pip-audit

echo "Installing the frontend dependencies for the audit."
cd "${REPOSITORY_ROOT}/frontend"
npm ci --no-audit --no-fund

echo "Auditing Node dependencies."
npm run audit:check
