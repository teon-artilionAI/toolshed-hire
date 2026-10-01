#!/usr/bin/env bash
#
# Build the frontend and deploy it to its Vercel project.
#
# The build happens here on the runner and the finished output is uploaded, so
# what is deployed is exactly what this commit built. The project is chosen by
# VERCEL_ORG_ID and VERCEL_PROJECT_ID, which differ between staging and
# production. Each project carries its own CLOUD_RUN_API_ORIGIN, which is what
# the /api rewrite in vercel.json points at.
#
# Output, written to GITHUB_OUTPUT:
#   deployment_url  the unique URL of this deployment

set -euo pipefail

: "${VERCEL_TOKEN:?VERCEL_TOKEN is not set}"
: "${VERCEL_ORG_ID:?VERCEL_ORG_ID is not set}"
: "${VERCEL_PROJECT_ID:?VERCEL_PROJECT_ID is not set}"
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
