#!/bin/sh
# Create the two uptime checks for Toolshed Hire (B3.1, NFR-05, C-43).
#
# The live check calls /api/health/live, which answers from the process and
# never opens a database session. It runs every five minutes from three
# regions, so a database that is asleep does not make the site look down.
#
# The full check calls /api/health, which queries Neon and confirms btree_gist.
# It runs once an hour, or once every three hours when the free compute
# allowance cannot carry an hourly wake. Check the Neon usage page before
# choosing, as B3.1 says, and pass FULL_PERIOD_SECONDS=10800 for the fallback.
#
# Both checks point at the hostname people use, not the Cloud Run run.app
# address, because the frontend is the only supported entrance.
#
# Usage:
#   UPTIME_HOST=toolshed-hire.vercel.app sh infra/scripts/create-uptime-checks.sh
#   UPTIME_HOST=toolshed-hire-staging.vercel.app FULL_PERIOD_SECONDS=10800 \
#     sh infra/scripts/create-uptime-checks.sh
#
# Requires: gcloud authenticated for the toolshed configuration, and the
# Monitoring Admin role on the project.

set -eu

PROJECT="${GCP_PROJECT:-toolshed-hire}"
CONFIGURATION="${GCLOUD_CONFIGURATION:-toolshed}"
HOST="${UPTIME_HOST:?Set UPTIME_HOST to the deployed hostname, for example toolshed-hire.vercel.app}"
FULL_PERIOD_SECONDS="${FULL_PERIOD_SECONDS:-3600}"
LIVE_PERIOD_SECONDS=300
TIMEOUT_SECONDS=10
REGIONS="usa-iowa,europe-west1,asia-pacific"
PROTOCOL="https"
LIVE_PATH="/api/health/live"
FULL_PATH="/api/health"

if [ "$FULL_PERIOD_SECONDS" != "3600" ] && [ "$FULL_PERIOD_SECONDS" != "10800" ]; then
  echo "FULL_PERIOD_SECONDS must be 3600 or 10800, got $FULL_PERIOD_SECONDS." >&2
  exit 2
fi

existing() {
  gcloud monitoring uptime list-configs \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --format="value(displayName)" 2>/dev/null || true
}

create_check() {
  name="$1"
  path="$2"
  period="$3"
  reason="$4"
  if existing | grep -Fxq "$name"; then
    echo "Already present: $name"
    return 0
  fi
  echo "Creating $name every ${period}s against ${PROTOCOL}://${HOST}${path}"
  gcloud monitoring uptime create "$name" \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --resource-type=uptime-url \
    --resource-labels="host=${HOST},project_id=${PROJECT}" \
    --protocol="$PROTOCOL" \
    --path="$path" \
    --period="$period" \
    --timeout="$TIMEOUT_SECONDS" \
    --regions="$REGIONS" \
    --status-codes=200 \
    --user-labels="application=toolshed-hire,purpose=${reason}"
}

create_check "Toolshed Hire liveness (${HOST})" "$LIVE_PATH" "$LIVE_PERIOD_SECONDS" "liveness"
create_check "Toolshed Hire full health (${HOST})" "$FULL_PATH" "$FULL_PERIOD_SECONDS" "full-health"

echo "Done. The full health check wakes Neon every ${FULL_PERIOD_SECONDS}s."
echo "Record the check names and the first availability figure in the pending operations note."
