#!/usr/bin/env bash
#
# Build the frontend and deploy it to its Vercel project.
#
# The build happens here on the runner and the finished output is uploaded, so
# what is deployed is exactly what this commit built. The project is chosen by
# VERCEL_ORG_ID and VERCEL_PROJECT_ID, which differ between staging and
# production.
#
# The /api rewrite in vercel.json names its target as $CLOUD_RUN_API_ORIGIN.
# This script writes the real address of the API that the same run just
# deployed into the runner's copy of that file before building, so the
# frontend can never be pointed at a different environment's API by a stale
# setting. The address is not committed and is not part of the bundle the
# browser downloads. It lives only in the routing configuration on Vercel.
#
# Output, written to GITHUB_OUTPUT:
#   deployment_url  the unique URL of this deployment

set -euo pipefail

: "${VERCEL_TOKEN:?VERCEL_TOKEN is not set}"
: "${VERCEL_ORG_ID:?VERCEL_ORG_ID is not set}"
: "${VERCEL_PROJECT_ID:?VERCEL_PROJECT_ID is not set}"
: "${API_ORIGIN:?API_ORIGIN is not set. The frontend has no API to route to.}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is not set. This script runs inside a GitHub Actions step.}"

# Pinned, so a new major version of the CLI cannot change the deployment.
VERCEL_CLI_VERSION="62.1.0"
VERCEL_TARGET="production"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPOSITORY_ROOT}/frontend"

vercel() {
  npx --yes "vercel@${VERCEL_CLI_VERSION}" "$@" --token="${VERCEL_TOKEN}"
}

echo "Pulling the ${VERCEL_TARGET} settings for the Vercel project."
vercel pull --yes --environment="${VERCEL_TARGET}"

echo "Pointing the /api rewrite at the API deployed by this run."
API_ORIGIN="${API_ORIGIN}" python3 - <<'PYTHON'
import json
import os
import sys
from pathlib import Path

PLACEHOLDER = "$CLOUD_RUN_API_ORIGIN"
origin = os.environ["API_ORIGIN"].rstrip("/")
path = Path("vercel.json")
config = json.loads(path.read_text(encoding="utf-8"))

replaced = 0
for rewrite in config.get("rewrites", []):
    destination = rewrite.get("destination", "")
    if PLACEHOLDER in destination:
        rewrite["destination"] = destination.replace(PLACEHOLDER, origin)
        rewrite.pop("env", None)
        replaced += 1

if replaced != 1:
    sys.exit(
        f"Expected exactly one rewrite using {PLACEHOLDER} in vercel.json and found "
        f"{replaced}. The /api rewrite would not reach the API, so the build stops here."
    )

path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
print("The /api rewrite now targets the deployed API.")
PYTHON

echo "Building."
vercel build --prod

echo "Deploying the built output."
deployment_url="$(vercel deploy --prebuilt --prod)"

if [ -z "${deployment_url}" ]; then
  echo "::error title=No deployment URL::Vercel accepted the deployment but returned no URL."
  exit 1
fi

echo "deployment_url=${deployment_url}" >> "${GITHUB_OUTPUT}"
echo "Deployed ${deployment_url}"
