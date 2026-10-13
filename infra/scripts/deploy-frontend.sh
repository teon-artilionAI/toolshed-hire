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
# API_ROUTE chooses how /api reaches the API (C-02, #96).
#   rewrite   the default. The rewrite forwards /api to the API's public
#             address, and frontend/api is removed before the build, so the
#             deployment carries no function.
#   function  the rewrite sends /api to the function in frontend/api, which
#             calls an API that requires IAM authentication with an ID token
#             it gets through Workload Identity Federation. The function runs
#             in London beside the API, and is given the API's address, the
#             Workload Identity provider and the invoker account as runtime
#             settings of this deployment. GCP_WORKLOAD_AUDIENCE and
#             GCP_INVOKER_ACCOUNT are required in this mode.
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
API_ROUTE="${API_ROUTE:-rewrite}"
# London, beside the API. From Vercel's default region in the United States the
# function added about 160 ms to every request (#96).
FUNCTION_REGION="lhr1"

case "${API_ROUTE}" in
  rewrite) ;;
  function)
    : "${GCP_WORKLOAD_AUDIENCE:?GCP_WORKLOAD_AUDIENCE is not set. The /api function cannot get an identity.}"
    : "${GCP_INVOKER_ACCOUNT:?GCP_INVOKER_ACCOUNT is not set. The /api function has no account to invoke the API as.}"
    ;;
  *)
    echo "::error title=Unknown API_ROUTE::API_ROUTE is '${API_ROUTE}'. It must be rewrite or function."
    exit 1
    ;;
esac

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPOSITORY_ROOT}/frontend"

vercel() {
  npx --yes "vercel@${VERCEL_CLI_VERSION}" "$@" --token="${VERCEL_TOKEN}"
}

echo "Pulling the ${VERCEL_TARGET} settings for the Vercel project."
vercel pull --yes --environment="${VERCEL_TARGET}"

echo "Routing /api through the ${API_ROUTE}."
API_ORIGIN="${API_ORIGIN}" API_ROUTE="${API_ROUTE}" python3 - <<'PYTHON'
import json
import os
import shutil
import sys
from pathlib import Path

PLACEHOLDER = "$CLOUD_RUN_API_ORIGIN"
origin = os.environ["API_ORIGIN"].rstrip("/")
path = Path("vercel.json")
config = json.loads(path.read_text(encoding="utf-8"))

replaced = 0
# The function's rewrite names the path parameter __path, so Vercel adds only
# that one to the query, and the function takes it out again.
FUNCTION_REWRITE = {"source": "/api/:__path*", "destination": "/api/proxy"}
use_function = os.environ["API_ROUTE"] == "function"
rewrites = config.get("rewrites", [])
for index, rewrite in enumerate(rewrites):
    destination = rewrite.get("destination", "")
    if PLACEHOLDER in destination:
        if use_function:
            rewrites[index] = dict(FUNCTION_REWRITE)
        else:
            rewrite["destination"] = destination.replace(PLACEHOLDER, origin)
            rewrite.pop("env", None)
        replaced += 1

if replaced != 1:
    sys.exit(
        f"Expected exactly one rewrite using {PLACEHOLDER} in vercel.json and found "
        f"{replaced}. The /api rewrite would not reach the API, so the build stops here."
    )

path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
if use_function:
    print("The /api rewrite now sends requests to the function.")
else:
    # Without this the deployment would carry a function nothing routes to,
    # which still answers on its own path.
    shutil.rmtree("api", ignore_errors=True)
    print("The /api rewrite now targets the deployed API, and the deployment carries no function.")
PYTHON

echo "Building."
vercel build --prod

echo "Deploying the built output."
deploy_flags=(--prebuilt --prod)
if [ "${API_ROUTE}" = "function" ]; then
  # Runtime settings of this deployment only. None of them is a secret, and the
  # API's address is masked in the log by deploy-api.sh.
  deploy_flags+=(
    --regions "${FUNCTION_REGION}"
    --env "API_SERVICE_URL=${API_ORIGIN}"
    --env "GCP_WORKLOAD_AUDIENCE=${GCP_WORKLOAD_AUDIENCE}"
    --env "GCP_INVOKER_ACCOUNT=${GCP_INVOKER_ACCOUNT}"
  )
fi
deployment_url="$(vercel deploy "${deploy_flags[@]}")"

if [ -z "${deployment_url}" ]; then
  echo "::error title=No deployment URL::Vercel accepted the deployment but returned no URL."
  exit 1
fi

echo "deployment_url=${deployment_url}" >> "${GITHUB_OUTPUT}"
echo "Deployed ${deployment_url}"
