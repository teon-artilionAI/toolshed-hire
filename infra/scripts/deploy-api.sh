#!/usr/bin/env bash
#
# Deploy one image to one Cloud Run service.
#
# With USE_CANDIDATE=true and an existing service, the new revision is deployed
# with no traffic under the tag "candidate", so it can be smoke tested on its
# own URL before any user reaches it. The caller then shifts traffic with
# promote-api.sh. On the very first deployment there is no existing revision to
# keep serving, so the revision takes traffic straight away.
#
# The repository is public, so its workflow logs are public too. The address of
# the service is therefore never written to the log. Browsers reach the API
# through the frontend domain, and that is the only address that is published.
# The address is masked as soon as it is known, and the output of the deploy
# command, which prints it, is filtered.
#
# Outputs, written to GITHUB_OUTPUT:
#   service_url     the stable URL of the service
#   check_url       the URL to smoke test (the candidate URL when one exists)
#   used_candidate  true when traffic still has to be shifted

set -euo pipefail

: "${IMAGE_DIGEST:?IMAGE_DIGEST is not set}"
: "${SERVICE_NAME:?SERVICE_NAME is not set}"
: "${REGION:?REGION is not set}"
: "${RUNTIME_SERVICE_ACCOUNT:?RUNTIME_SERVICE_ACCOUNT is not set}"
: "${ENVIRONMENT_NAME:?ENVIRONMENT_NAME is not set}"
: "${FRONTEND_ORIGIN:?FRONTEND_ORIGIN is not set}"
: "${EMAIL_ALLOWED_RECIPIENT:?EMAIL_ALLOWED_RECIPIENT is not set}"
: "${DATABASE_URL_SECRET:?DATABASE_URL_SECRET is not set}"
: "${JWT_SECRET_NAME:?JWT_SECRET_NAME is not set}"
: "${RESEND_API_KEY_SECRET:?RESEND_API_KEY_SECRET is not set}"
: "${CLOUD_RUN_MAX_INSTANCES:?CLOUD_RUN_MAX_INSTANCES is not set}"
: "${GITHUB_SHA:?GITHUB_SHA is not set}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is not set. This script runs inside a GitHub Actions step.}"

USE_CANDIDATE="${USE_CANDIDATE:-false}"
CANDIDATE_TAG="candidate"

CLOUD_RUN_MIN_INSTANCES="${CLOUD_RUN_MIN_INSTANCES:-0}"
CLOUD_RUN_CPU="${CLOUD_RUN_CPU:-1}"
CLOUD_RUN_MEMORY="${CLOUD_RUN_MEMORY:-512Mi}"
CLOUD_RUN_CONCURRENCY="${CLOUD_RUN_CONCURRENCY:-80}"
CLOUD_RUN_REQUEST_TIMEOUT="${CLOUD_RUN_REQUEST_TIMEOUT:-60s}"
CLOUD_RUN_PORT="${CLOUD_RUN_PORT:-8080}"

# The suffix carries the run number and attempt, so running the same deployment
# again does not collide with the revision the first attempt created.
revision_suffix="${GITHUB_SHA::7}-${GITHUB_RUN_NUMBER:-0}-${GITHUB_RUN_ATTEMPT:-1}"

# Replaces anything that looks like a Cloud Run address in what a command
# prints. The first deployment prints the address before this script could
# know it, so masking alone is not enough.
hide_service_urls() {
  sed -E 's#https://[A-Za-z0-9.-]+\.run\.app#[service address hidden]#g'
}

# Tells GitHub to redact one value from the rest of the log.
mask() {
  if [ -n "${1}" ]; then
    echo "::add-mask::${1}"
    echo "::add-mask::${1#https://}"
  fi
}

existing_url="$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --format="value(status.url)" 2>/dev/null || true)"
mask "${existing_url}"

traffic_flags=()
used_candidate="false"
if [ "${USE_CANDIDATE}" = "true" ] && [ -n "${existing_url}" ]; then
  traffic_flags=(--no-traffic "--tag=${CANDIDATE_TAG}")
  used_candidate="true"
  echo "Deploying ${IMAGE_DIGEST} to ${SERVICE_NAME} as a candidate with no traffic."
else
  echo "Deploying ${IMAGE_DIGEST} to ${SERVICE_NAME} with traffic."
fi

# Secrets are mounted from Secret Manager into the revision, so no secret value
# passes through this script or its log. The runtime service account is a
# separate, least privileged identity from the one running this deployment.
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE_DIGEST}" \
  --region="${REGION}" \
  --platform=managed \
  --service-account="${RUNTIME_SERVICE_ACCOUNT}" \
  --port="${CLOUD_RUN_PORT}" \
  --cpu="${CLOUD_RUN_CPU}" \
  --memory="${CLOUD_RUN_MEMORY}" \
  --concurrency="${CLOUD_RUN_CONCURRENCY}" \
  --timeout="${CLOUD_RUN_REQUEST_TIMEOUT}" \
  --min-instances="${CLOUD_RUN_MIN_INSTANCES}" \
  --max-instances="${CLOUD_RUN_MAX_INSTANCES}" \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=${ENVIRONMENT_NAME},CORS_ORIGINS=${FRONTEND_ORIGIN},EMAIL_ALLOWED_RECIPIENT=${EMAIL_ALLOWED_RECIPIENT}" \
  --set-secrets="DATABASE_URL=${DATABASE_URL_SECRET}:latest,JWT_SECRET=${JWT_SECRET_NAME}:latest,RESEND_API_KEY=${RESEND_API_KEY_SECRET}:latest" \
  --revision-suffix="${revision_suffix}" \
  "${traffic_flags[@]}" \
  --quiet 2>&1 | hide_service_urls

service_url="$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --format="value(status.url)")"

if [ -z "${service_url}" ]; then
  echo "::error title=No service URL::Cloud Run reported no URL for ${SERVICE_NAME} after a successful deploy, so there is nothing to smoke test."
  exit 1
fi
mask "${service_url}"

check_url="${service_url}"
if [ "${used_candidate}" = "true" ]; then
  check_url="$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --format="value(status.traffic.filter(\"tag:${CANDIDATE_TAG}\").extract(url).flatten())")"
  if [ -z "${check_url}" ]; then
    echo "::error title=No candidate URL::The candidate revision was deployed but Cloud Run lists no URL for the ${CANDIDATE_TAG} tag."
    exit 1
  fi
  mask "${check_url}"
fi

{
  echo "service_url=${service_url}"
  echo "check_url=${check_url}"
  echo "used_candidate=${used_candidate}"
} >> "${GITHUB_OUTPUT}"

echo "Deployed. The service address is kept out of this log on purpose."
