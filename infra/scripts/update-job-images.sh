#!/usr/bin/env bash
#
# Point the maintenance jobs of an environment at the image just deployed.
#
# The anonymise and session pruning jobs (B9.2, B9.6) run on a schedule from an
# image named by digest. Left alone, a job keeps the image it was created with
# until the Artifact Registry cleanup policy deletes it, and then every run
# fails with "image not found". That happened on staging on 25 October 2026.
# Run after each deploy, the jobs always run the same code as the service and
# always use an image the policy keeps.
#
# Required environment:
#   SERVICE_NAME  The Cloud Run service, toolshed-api-staging or toolshed-api-prod
#   REGION        The region of the service and its jobs
#   IMAGE_DIGEST  The image just deployed, named by digest
#
# An environment whose jobs have not been created yet is skipped with a notice,
# so this step never blocks a deploy that precedes create-maintenance-jobs.sh.

set -euo pipefail

: "${SERVICE_NAME:?SERVICE_NAME is not set}"
: "${REGION:?REGION is not set}"
: "${IMAGE_DIGEST:?IMAGE_DIGEST is not set}"

SERVICE_PREFIX="toolshed-api-"
environment="${SERVICE_NAME#"${SERVICE_PREFIX}"}"
if [ "${environment}" = "${SERVICE_NAME}" ]; then
  echo "::error title=Unexpected service name::${SERVICE_NAME} does not start with ${SERVICE_PREFIX}, so the job names cannot be worked out."
  exit 1
fi

for job in "toolshed-anonymise-customers-${environment}" "toolshed-prune-sessions-${environment}"; do
  if ! output="$(gcloud run jobs describe "${job}" --region="${REGION}" --format="value(name)" 2>&1)"; then
    case "${output}" in
      # gcloud says "Cannot find job [name]" for a job that does not exist.
      *"Cannot find job"* | *NOT_FOUND* | *"not found"* | *"could not be found"*)
        echo "::notice title=Job not created yet::${job} does not exist, so its image was not updated. Run create-maintenance-jobs.sh to create it."
        continue
        ;;
      *)
        # A denied or failed read is not a missing job. Fail so it is seen.
        echo "::error title=Job discovery failed::Could not read ${job}: ${output}"
        exit 1
        ;;
    esac
  fi
  echo "Pointing ${job} at ${IMAGE_DIGEST}."
  gcloud run jobs update "${job}" --region="${REGION}" --image="${IMAGE_DIGEST}" --quiet > /dev/null
done
