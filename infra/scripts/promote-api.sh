#!/usr/bin/env bash
#
# Move all traffic to the newest revision of a Cloud Run service.
#
# This runs only after the candidate revision has passed its smoke test. Until
# this point the previous revision was still serving every request, so a failed
# candidate never reached a user.

set -euo pipefail

: "${SERVICE_NAME:?SERVICE_NAME is not set}"
: "${REGION:?REGION is not set}"

echo "Shifting all traffic on ${SERVICE_NAME} to the latest revision."
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region="${REGION}" \
  --to-latest \
  --quiet 2>&1 | sed -E 's#https://[A-Za-z0-9.-]+\.run\.app#[service address hidden]#g'
