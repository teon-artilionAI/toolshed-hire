#!/bin/sh
# Recreate the Toolshed Hire liveness check and the hourly full-health job (B3.1).
#
# The liveness check calls /api/health/live every five minutes from three
# regions. It does not open a database session, so a sleeping Neon database
# does not make the service look down.
#
# The full check calls /api/health hourly through Cloud Scheduler. Cloud
# Monitoring uptime checks accept only 1, 5, 10 or 15 minute periods, so an
# hourly check cannot be an uptime check. The scheduler job is the chosen
# design recorded in results/B3/B3.1-uptime-partial.md.
#
# It also creates the alert policy that emails the owner when the liveness
# check fails from more than one region, which is Google's recommended
# condition. One region failing alone is usually that region's network.
#
# Usage:
#   UPTIME_HOST=toolshed-hire-staging.vercel.app \
#     sh infra/scripts/create-uptime-checks.sh
#
# The script is idempotent: an existing liveness check is left alone, and an
# existing scheduler job is updated in place. A failed read-back exits non-zero.
#
# Requires gcloud authenticated for the toolshed configuration, with
# Monitoring Admin and Cloud Scheduler Admin on the project.

set -eu

PROJECT="${GCP_PROJECT:-toolshed-hire}"
CONFIGURATION="${GCLOUD_CONFIGURATION:-toolshed}"
HOST="${UPTIME_HOST:?Set UPTIME_HOST to the deployed hostname, for example toolshed-hire-staging.vercel.app}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-staging}"
LOCATION="${SCHEDULER_LOCATION:-europe-west2}"
SCHEDULE="${FULL_SCHEDULE:-0 * * * *}"
TIME_ZONE="${FULL_TIME_ZONE:-Africa/Johannesburg}"
LIVE_NAME="Toolshed Hire liveness (${HOST})"
JOB_NAME="toolshed-full-health-${ENVIRONMENT_NAME}"
LIVE_PATH="/api/health/live"
FULL_PATH="/api/health"
REGIONS="usa-iowa,europe,asia-pacific"

if [ -z "$SCHEDULE" ]; then
  echo "FULL_SCHEDULE must not be empty." >&2
  exit 2
fi

liveness_names() {
  gcloud monitoring uptime list-configs \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --format="value(displayName)"
}

if ! names="$(liveness_names 2>&1)"; then
  echo "::error title=Liveness discovery failed::Could not list uptime checks. A denied or unavailable discovery is not a missing check, so nothing was created." >&2
  printf '%s\n' "$names" >&2
  exit 1
fi

if printf '%s\n' "$names" | grep -Fxq "$LIVE_NAME"; then
  echo "Already present: $LIVE_NAME"
else
  echo "Creating $LIVE_NAME every 5 minutes from $REGIONS"
  gcloud monitoring uptime create "$LIVE_NAME" \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --resource-type=uptime-url \
    --resource-labels="host=${HOST},project_id=${PROJECT}" \
    --protocol=https \
    --path="$LIVE_PATH" \
    --period=5 \
    --timeout=10 \
    --regions="$REGIONS" \
    --status-codes=200 \
    --user-labels="application=toolshed-hire,purpose=liveness"
fi

CHANNEL_NAME="Toolshed Hire owner email"
UPTIME_POLICY_NAME="Toolshed Hire: liveness failing (${HOST})"
# A failure from two or more of the three regions fires the alert.
FAILING_REGIONS_THRESHOLD=1

check_id="$(gcloud monitoring uptime list-configs   --project="$PROJECT" --configuration="$CONFIGURATION"   --filter="displayName=\"$LIVE_NAME\"" --format="value(name.basename())" | head -n 1)"
if [ -z "$check_id" ]; then
  echo "::error title=Liveness check missing::The liveness check $LIVE_NAME could not be read back, so no alert policy was created." >&2
  exit 1
fi

channel="$(gcloud beta monitoring channels list   --project="$PROJECT" --configuration="$CONFIGURATION"   --filter="displayName=\"$CHANNEL_NAME\"" --format="value(name)" | head -n 1)"
if [ -z "$channel" ]; then
  echo "::error title=Channel missing::Run create-alert-policies.sh first, which creates the owner email channel." >&2
  exit 1
fi

existing_policy="$(gcloud monitoring policies list   --project="$PROJECT" --configuration="$CONFIGURATION"   --filter="displayName=\"$UPTIME_POLICY_NAME\"" --format="value(name)" | head -n 1)"
if [ -n "$existing_policy" ]; then
  echo "Already present: $UPTIME_POLICY_NAME"
else
  echo "Creating $UPTIME_POLICY_NAME"
  gcloud monitoring policies create     --project="$PROJECT" --configuration="$CONFIGURATION"     --display-name="$UPTIME_POLICY_NAME"     --notification-channels="$channel"     --combiner=OR     --condition-display-name="$UPTIME_POLICY_NAME"     --condition-filter="metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id=\"$check_id\" AND resource.type=\"uptime_url\""     --aggregation="{\"alignmentPeriod\":\"1200s\",\"perSeriesAligner\":\"ALIGN_NEXT_OLDER\",\"crossSeriesReducer\":\"REDUCE_COUNT_FALSE\",\"groupByFields\":[\"resource.label.host\"]}"     --duration=60s     --if="> $FAILING_REGIONS_THRESHOLD"     --trigger-count=1     --documentation="The liveness route of $HOST failed from more than one region. Open $HOST/api/health/live, then the Cloud Run revision's logs. The incident procedure says what to do next."
fi

SCHEDULER_HEADER="User-Agent=Google-Cloud-Scheduler"

scheduler_args() {
  printf '%s\n' \
    "--project=$PROJECT" \
    "--configuration=$CONFIGURATION" \
    "--location=$LOCATION" \
    "--time-zone=$TIME_ZONE" \
    "--uri=https://${HOST}${FULL_PATH}" \
    "--http-method=GET" \
\
    "--attempt-deadline=60s" \
    "--max-retry-attempts=5" \
    "--min-backoff=5s" \
    "--max-backoff=3600s" \
    "--max-doublings=5" \
    "--max-retry-duration=0s"
}

scheduler_state() {
  local output
  if output="$(gcloud scheduler jobs describe "$JOB_NAME" \
      --project="$PROJECT" --configuration="$CONFIGURATION" \
      --location="$LOCATION" 2>&1)"; then
    echo present
    return 0
  fi
  case "$output" in
    *NOT_FOUND*|*"not found"*|*"does not exist"*|*"NOT FOUND"*)
      echo absent
      return 0
      ;;
    *)
      echo "::error title=Scheduler discovery failed::Could not read the job. A denied or unavailable discovery is not a missing job, so nothing was created." >&2
      printf '%s\n' "$output" >&2
      return 1
      ;;
  esac
}

state="$(scheduler_state)" || exit 1
if [ "$state" = "present" ]; then
  echo "Updating Cloud Scheduler job: $JOB_NAME"
  # shellcheck disable=SC2046
  # update names the header flag --update-headers where create uses --headers.
  gcloud scheduler jobs update http "$JOB_NAME" --schedule="$SCHEDULE"     --update-headers="$SCHEDULER_HEADER" $(scheduler_args)
else
  echo "Creating Cloud Scheduler job: $JOB_NAME"
  # shellcheck disable=SC2046
  gcloud scheduler jobs create http "$JOB_NAME" --schedule="$SCHEDULE"     --headers="$SCHEDULER_HEADER" $(scheduler_args)
fi

echo "Liveness check:"
gcloud monitoring uptime list-configs \
  --project="$PROJECT" --configuration="$CONFIGURATION" \
  --filter="displayName=\"$LIVE_NAME\"" \
  --format="value(displayName,period,httpCheck.path)"

echo "Full-health scheduler job:"
gcloud scheduler jobs describe "$JOB_NAME" \
  --project="$PROJECT" --configuration="$CONFIGURATION" \
  --location="$LOCATION" \
  --format="value(state,schedule,timeZone,httpTarget.uri)"

echo "Done. The full health job wakes Neon on schedule ${SCHEDULE} (${TIME_ZONE})."
