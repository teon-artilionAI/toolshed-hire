#!/usr/bin/env bash
#
# Smoke test a deployed revision.
#
# A deployment is not finished until something has proved the deployed revision
# answers correctly. Without this, a green workflow means only that gcloud
# accepted the request, which is a much weaker claim than it appears to be.
#
# The contract asserted here is the one app/api/routers/health.py implements:
#   GET  ${SERVICE_URL}/api/health
#   200  with a JSON body carrying "status": "healthy"
#
# The endpoint answers 503 with "status": "degraded" when the database is
# unreachable or btree_gist is missing, so both the code and the body are
# checked. Checking the code alone would pass a revision that cannot enforce
# the exclusion constraint, which is the one thing this system exists to do.
#
# The path lives under /api so that the same URL works through the Vercel
# rewrite and directly against Cloud Run.
#
# Required environment:
#   SERVICE_URL   Origin of the deployed service, no trailing slash
#
# Optional environment, with defaults chosen to allow for a cold start on a
# service that scales to zero:
#   HEALTH_PATH                          default /api/health
#   SMOKE_TEST_MAX_ATTEMPTS              default 12
#   SMOKE_TEST_RETRY_DELAY_SECONDS       default 10
#   SMOKE_TEST_REQUEST_TIMEOUT_SECONDS   default 20

# -e is deliberately not set. A failing curl is an expected outcome of an
# attempt, not a reason to abandon the retry loop.
set -uo pipefail

: "${SERVICE_URL:?SERVICE_URL is not set. There is nothing to smoke test.}"

HEALTH_PATH="${HEALTH_PATH:-/api/health}"
SMOKE_TEST_MAX_ATTEMPTS="${SMOKE_TEST_MAX_ATTEMPTS:-12}"
SMOKE_TEST_RETRY_DELAY_SECONDS="${SMOKE_TEST_RETRY_DELAY_SECONDS:-10}"
SMOKE_TEST_REQUEST_TIMEOUT_SECONDS="${SMOKE_TEST_REQUEST_TIMEOUT_SECONDS:-20}"

EXPECTED_STATUS_CODE="200"
EXPECTED_BODY_PATTERN='"status"[[:space:]]*:[[:space:]]*"healthy"'

url="${SERVICE_URL}${HEALTH_PATH}"
response_body="$(mktemp)"
trap 'rm -f "${response_body}"' EXIT

echo "Smoke testing ${url}"

status_code="000"
attempt=1
while [ "${attempt}" -le "${SMOKE_TEST_MAX_ATTEMPTS}" ]; do
  status_code="$(curl \
    --silent \
    --show-error \
    --location \
    --max-time "${SMOKE_TEST_REQUEST_TIMEOUT_SECONDS}" \
    --output "${response_body}" \
    --write-out '%{http_code}' \
    "${url}" || echo "000")"

  if [ "${status_code}" = "${EXPECTED_STATUS_CODE}" ] \
    && grep -qE "${EXPECTED_BODY_PATTERN}" "${response_body}"; then
    echo "Attempt ${attempt}: healthy."
    echo "Response: $(cat "${response_body}")"
    exit 0
  fi

  echo "Attempt ${attempt} of ${SMOKE_TEST_MAX_ATTEMPTS}: HTTP ${status_code}. Retrying in ${SMOKE_TEST_RETRY_DELAY_SECONDS}s."
  attempt=$((attempt + 1))
  if [ "${attempt}" -le "${SMOKE_TEST_MAX_ATTEMPTS}" ]; then
    sleep "${SMOKE_TEST_RETRY_DELAY_SECONDS}"
  fi
done

echo "::error title=Smoke test failed::${url} did not report healthy within ${SMOKE_TEST_MAX_ATTEMPTS} attempts over roughly $((SMOKE_TEST_MAX_ATTEMPTS * SMOKE_TEST_RETRY_DELAY_SECONDS)) seconds. Last HTTP status was ${status_code}. Expected ${EXPECTED_STATUS_CODE} with a JSON body carrying \"status\": \"healthy\". A 503 with \"status\": \"degraded\" means the revision started but its database is unreachable or btree_gist is missing."
echo "Last response body:"
cat "${response_body}" 2>/dev/null || echo "(no response body was received)"
echo
echo "The previous Cloud Run revision is still deployed and can take traffic."
echo "Roll back by listing revisions and shifting traffic back:"
echo "  gcloud run revisions list --service=SERVICE --region=REGION"
echo "  gcloud run services update-traffic SERVICE --region=REGION --to-revisions=PREVIOUS=100"
exit 1
