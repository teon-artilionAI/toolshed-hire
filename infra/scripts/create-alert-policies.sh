#!/bin/sh
# Create or replace the log based metrics and alert policies for Toolshed Hire
# (B3.2, B3.7, C-43).
#
# The metrics are DELTA/INT64 counters: each aligned point carries the number
# of matching log events in that sample. The policies therefore sum the counter
# values with ALIGN_SUM and REDUCE_SUM, rather than counting samples with
# ALIGN_COUNT. The condition duration is zero, so a window above its threshold
# triggers immediately instead of requiring a second sustained window.
#
# The actual cloud policy changes are operational. Run this only after the
# signed-in Google Cloud configuration has the Monitoring Admin role. The
# script is idempotent for the email channel and metrics. An existing policy is
# left alone by default; set REPLACE_EXISTING=1 to delete and recreate it with
# the corrected definition.
#
#   PROJECT=toolshed-hire OWNER=teon@sulako.com \
#     REPLACE_EXISTING=1 sh infra/scripts/create-alert-policies.sh
#
# Do not run this as part of a test. B3.2 requires an authorised live action.

set -eu

PROJECT="${PROJECT:-toolshed-hire}"
OWNER="${OWNER:-teon@sulako.com}"
CONFIGURATION="${GCLOUD_CONFIGURATION:-toolshed}"
METRICS_ONLY="${METRICS_ONLY:-0}"
REPLACE_EXISTING="${REPLACE_EXISTING:-0}"
CHANNEL_NAME="Toolshed Hire owner email"

channel_id() {
  gcloud beta monitoring channels list \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --filter="displayName=\"$CHANNEL_NAME\"" \
    --format="value(name)" 2>/dev/null | head -n 1
}

CHANNEL="$(channel_id)"
if [ -z "$CHANNEL" ]; then
  echo "Creating the email notification channel for $OWNER"
  CHANNEL="$(gcloud beta monitoring channels create \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --type=email --display-name="$CHANNEL_NAME" \
    --channel-labels="email_address=$OWNER" \
    --format="value(name)")"
fi
echo "Notification channel: $CHANNEL"

metric() {
  name="$1"
  description="$2"
  filter="$3"
  if gcloud logging metrics describe "$name" --project="$PROJECT" \
      --configuration="$CONFIGURATION" >/dev/null 2>&1; then
    echo "Metric already exists: $name"
  else
    gcloud logging metrics create "$name" \
      --project="$PROJECT" --configuration="$CONFIGURATION" \
      --description="$description" --log-filter="$filter"
  fi
}

policy_exists() {
  gcloud monitoring policies list \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --filter="displayName=\"$1\"" --format="value(name)" 2>/dev/null | head -n 1
}

policy() {
  name="$1"
  metric_name="$2"
  window_seconds="$3"
  comparison="$4"
  threshold="$5"
  documentation="$6"
  if [ "$METRICS_ONLY" = "1" ]; then
    return 0
  fi
  existing="$(policy_exists "$name")"
  if [ -n "$existing" ]; then
    if [ "$REPLACE_EXISTING" != "1" ]; then
      echo "Policy already exists: $name (set REPLACE_EXISTING=1 to replace it)"
      return 0
    fi
    echo "Replacing policy: $name"
    gcloud monitoring policies delete "$existing" \
      --project="$PROJECT" --configuration="$CONFIGURATION" --quiet
  fi
  gcloud monitoring policies create \
    --project="$PROJECT" --configuration="$CONFIGURATION" \
    --display-name="$name" \
    --notification-channels="$CHANNEL" \
    --combiner=OR \
    --condition-display-name="$name" \
    --condition-filter="metric.type=\"logging.googleapis.com/user/$metric_name\" AND resource.type=\"cloud_run_revision\"" \
    --aggregation="{\"alignmentPeriod\":\"${window_seconds}s\",\"perSeriesAligner\":\"ALIGN_SUM\",\"crossSeriesReducer\":\"REDUCE_SUM\"}" \
    --duration=0s \
    --if="$comparison $threshold" \
    --trigger-count=1 \
    --documentation="$documentation"
}

# A refresh token presented twice is a stolen or reused cookie. Any occurrence
# in five minutes is worth a person looking.
metric "auth_refresh_reuse" \
  "Refresh token reuse detected" \
  'jsonPayload.message="auth.refresh_reuse_detected"'
policy "Toolshed Hire: refresh token reuse" "auth_refresh_reuse" 300 ">" 0 \
  "A refresh token was presented more than once. Treat it as a possible session theft. Read the audit event and revoke the family."

# Five lockouts in ten minutes is above ordinary forgotten-password traffic.
metric "auth_account_lockouts" \
  "Account lockouts" \
  'jsonPayload.message="auth.account_locked"'
policy "Toolshed Hire: account lockouts" "auth_account_lockouts" 600 ">=" 5 \
  "Five or more accounts locked in ten minutes. Check the source addresses and the sign-in log before changing anything."

# The breach check fails open. One timeout is a transient provider problem.
# Two or more in ten minutes means the provider is unavailable and passwords
# are being accepted without screening.
metric "auth_breach_check_unavailable" \
  "Breached-password check unavailable" \
  'jsonPayload.message="auth.breach_check_unavailable"'
policy "Toolshed Hire: breached-password check unavailable" "auth_breach_check_unavailable" 600 ">" 1 \
  "The breached-password check could not reach Have I Been Pwned, so the fail-open path accepted the password. Two or more failures in ten minutes means a provider outage or a persistent network fault. Check the provider status and decide whether to keep registration and reset open."

# A refusal is expected now and then. Twenty in ten minutes is a pattern.
metric "api_refusals" \
  "API refusals" \
  'jsonPayload.message="api.domain_error"'
policy "Toolshed Hire: refusal rate" "api_refusals" 600 ">=" 20 \
  "Twenty or more domain refusals in ten minutes. Read the codes and paths. A single client or a broken screen usually explains it."

# A constraint violation is a write the database refused. One is a defect.
metric "database_constraint_violation" \
  "Database constraint violations" \
  'jsonPayload.message="api.domain_error" AND jsonPayload.error_message=~"constraint"'
policy "Toolshed Hire: database constraint violation" "database_constraint_violation" 300 ">" 0 \
  "The database refused a write on a constraint. Reproduce it with the request id and add a test before closing it."

# B3.7: the startup warning that email is off because the Resend key is
# missing. It is the compensating control for the C-33 deviation.
metric "email_switched_off" \
  "Email switched off because the Resend key is missing" \
  'jsonPayload.message="notification.email_not_configured"'
policy "Toolshed Hire: email is switched off" "email_switched_off" 300 ">" 0 \
  "The service started without a Resend key, so confirmations are recorded as failed. Restore the key version or record the deviation."

echo "Metrics and policies are defined. The uptime failure policy remains a separate action after the check ids exist."
