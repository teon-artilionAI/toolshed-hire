#!/usr/bin/env bash
#
# Set the cleanup policy of the Artifact Registry repository (NFR-18).
#
#   bash infra/scripts/set-image-retention.sh <project> <repository>
#
# Three rules, applied together:
#
#   keep-releases  Every image tagged vX.Y.Z is kept for good. The production
#                  workflow pushes each release under its tag, so the image of
#                  the previous release is always there to roll back to. The
#                  first rollback attempt on 24 October 2026 failed because
#                  the old policy had deleted that image.
#   keep-recent    The five newest images are kept whatever their age, which
#                  covers the staging revisions a staging rollback would use.
#   delete-old     Anything else older than seven days is deleted, which keeps
#                  the repository near the free storage allowance.
#
# Keep rules win over the delete rule. Commit tags are hexadecimal and never
# start with v, so only release images match keep-releases.
#
# Every gcloud command carries --configuration=toolshed, so the account comes
# from that named configuration and never from whichever one happens to be
# active.

set -euo pipefail

REGION="europe-west2"
FORBIDDEN_PROJECT="fred-ai-prod-480815"
RECENT_IMAGES_KEPT=5

if [ "$#" -ne 2 ]; then
  echo "Usage: bash infra/scripts/set-image-retention.sh <project> <repository>" >&2
  exit 2
fi

project="$1"
repository="$2"

if [ "${project}" = "${FORBIDDEN_PROJECT}" ]; then
  echo "Refusing to touch ${FORBIDDEN_PROJECT}. It belongs to another product. Pass the Toolshed Hire project." >&2
  exit 1
fi

policy_file="$(mktemp)"
trap 'rm -f "${policy_file}"' EXIT
cat > "${policy_file}" <<JSON
[
  {"name": "keep-releases", "action": {"type": "Keep"}, "condition": {"tagState": "tagged", "tagPrefixes": ["v"]}},
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": ${RECENT_IMAGES_KEPT}}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "7d"}}
]
JSON

echo "Setting the cleanup policy of ${repository} in ${project}."
gcloud artifacts repositories set-cleanup-policies "${repository}" \
  --configuration=toolshed --quiet --project="${project}" --location="${REGION}" \
  --policy="${policy_file}" --no-dry-run > /dev/null

gcloud artifacts repositories describe "${repository}" \
  --configuration=toolshed --project="${project}" --location="${REGION}" \
  --format="yaml(cleanupPolicies)"
