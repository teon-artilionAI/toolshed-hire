#!/usr/bin/env bash
#
# Create or update the two maintenance jobs of one environment and the
# schedules that start them (#113, #90).
#
#   bash infra/scripts/create-maintenance-jobs.sh <project> <environment> <image>
#
#   project      the Google Cloud project of the environment
#   environment  staging or prod, the short name the secrets carry
#   image        the API image to run, by digest, for example
#                europe-west2-docker.pkg.dev/<project>/toolshed/api@sha256:...
#
# Both jobs run the API image with another command, so they always run the
# code of the revision they were deployed with. Pass the digest the service
# runs now, and run this again after each release.
#
#   toolshed-anonymise-customers-<environment>
#       python -m app.jobs.anonymise_customers
#       Removes the personal details of customers whose last hire ended more
#       than two years ago and who have not signed in for as long, a hundred
#       to a transaction. It runs as the API's runtime identity and connects
#       with <environment>-database-url, the application role, which writes
#       and never deletes. Its schedule starts it at 02:00 Cape Town time on
#       the 1st of each month.
#
#   toolshed-prune-sessions-<environment>
#       python -m app.jobs.prune_refresh_sessions
#       Deletes the refresh sessions that expired more than ninety days ago,
#       five hundred to a transaction. It runs as an operator identity of its
#       own, toolshed-ops-run-<environment>, which may read one secret,
#       <environment>-database-migration-url, the role that owns the tables and
#       may delete. The API's runtime identity is never given that secret. Its
#       schedule starts it at 03:00 Cape Town time every Sunday.
#
# Each schedule calls the Cloud Run API as toolshed-scheduler-<environment>,
# which may run these two jobs and nothing else. Every secret reaches a job as
# a Secret Manager reference, so no value passes through this script, its
# arguments or its output.
#
# The schedule of the anonymisation is created paused, and a later run of this
# script leaves it as it is. Before resuming it, run the job once in report
# mode, which lists how many customers it would anonymise and their keys in
# the job's log and changes nothing:
#
#   gcloud run jobs execute toolshed-anonymise-customers-<environment> \
#     --configuration=toolshed --project=<project> --region=europe-west2 --wait \
#     --args=-m,app.jobs.anonymise_customers,--report
#
# and once the log reads right:
#
#   gcloud scheduler jobs resume toolshed-anonymise-customers-<environment> \
#     --configuration=toolshed --project=<project> --location=europe-west2
#
# The script can be run again at any time. A job or a schedule that exists is
# updated to what is written here, and a grant that exists is left as it is.
#
# Every gcloud command carries --configuration=toolshed, so the account comes
# from that named configuration and never from whichever one happens to be
# active, and every command names the project it was given. The script prints
# the names it was given and what it did, and nothing else.

set -euo pipefail

REGION="europe-west2"
TIME_ZONE="Africa/Johannesburg"
ANONYMISE_SCHEDULE="0 2 1 * *"
PRUNE_SCHEDULE="0 3 * * 0"
JOB_CPU="1"
JOB_MEMORY="512Mi"
JOB_TASK_TIMEOUT="3600s"
JOB_MAX_RETRIES="1"
# A project that belongs to another product and must never be changed from here.
FORBIDDEN_PROJECT="fred-ai-prod-480815"
REQUIRED_SERVICES=(run.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com iam.googleapis.com)
INVOKER_ROLE="roles/run.invoker"
SECRET_ROLE="roles/secretmanager.secretAccessor"
LOG_ROLE="roles/logging.logWriter"

usage() {
  echo "Usage: bash infra/scripts/create-maintenance-jobs.sh <project> <environment> <image>" >&2
  echo "The environment is staging or prod." >&2
}

if [ "$#" -ne 3 ]; then
  usage
  exit 2
fi

project="$1"
environment="$2"
image="$3"

if [ "${project}" = "${FORBIDDEN_PROJECT}" ]; then
  echo "Refusing to touch ${FORBIDDEN_PROJECT}. It belongs to another product. Pass the Toolshed Hire project." >&2
  exit 1
fi

if ! [[ "${project}" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "'${project}' is not a Google Cloud project id." >&2
  exit 2
fi

case "${environment}" in
  staging | prod) ;;
  *)
    echo "The environment must be staging or prod, not '${environment}'. The secrets of production carry the prefix prod." >&2
    usage
    exit 2
    ;;
esac

# An image in Artifact Registry, named by digest, so a schedule months from now
# runs exactly what was deployed today and not whatever a tag points at then.
if ! [[ "${image}" =~ ^[a-z0-9-]+-docker\.pkg\.dev/[a-z0-9./_-]+@sha256:[0-9a-f]{64}$ ]]; then
  echo "'${image}' is not an Artifact Registry image named by its digest." >&2
  exit 2
fi

# The named configuration has to exist. Without it gcloud would fall back to
# nothing at all, and the error it gives does not say why.
if ! gcloud config configurations describe toolshed \
  --configuration=toolshed > /dev/null 2>&1; then
  echo "There is no gcloud configuration named toolshed. Create it with 'gcloud config configurations create toolshed' and sign in." >&2
  exit 1
fi

anonymise_job="toolshed-anonymise-customers-${environment}"
prune_job="toolshed-prune-sessions-${environment}"
runtime_account="toolshed-api-run-${environment}@${project}.iam.gserviceaccount.com"
operator_name="toolshed-ops-run-${environment}"
operator_account="${operator_name}@${project}.iam.gserviceaccount.com"
scheduler_name="toolshed-scheduler-${environment}"
scheduler_account="${scheduler_name}@${project}.iam.gserviceaccount.com"
application_secret="${environment}-database-url"
operator_secret="${environment}-database-migration-url"

echo "Project ${project}, environment ${environment}, region ${REGION}."

echo "Enabling ${REQUIRED_SERVICES[*]} where they are not on already."
gcloud services enable "${REQUIRED_SERVICES[@]}" \
  --configuration=toolshed --quiet --project="${project}" > /dev/null

# Creates a service account when it is missing. One that exists is left as it is.
ensure_account() {
  local name="$1" address="$2" display_name="$3"
  if gcloud iam service-accounts describe "${address}" \
    --configuration=toolshed --quiet --project="${project}" > /dev/null 2>&1; then
    echo "The service account ${name} exists already."
  else
    echo "Creating the service account ${name}."
    gcloud iam service-accounts create "${name}" \
      --configuration=toolshed --quiet --project="${project}" \
      --display-name="${display_name}" > /dev/null
  fi
}

ensure_account "${operator_name}" "${operator_account}" "Toolshed Hire operator jobs, ${environment}"
ensure_account "${scheduler_name}" "${scheduler_account}" "Toolshed Hire job schedules, ${environment}"

echo "Granting ${LOG_ROLE} to ${operator_name}, as the runtime identity holds it."
gcloud projects add-iam-policy-binding "${project}" \
  --configuration=toolshed --quiet \
  --member="serviceAccount:${operator_account}" \
  --role="${LOG_ROLE}" --condition=None > /dev/null

echo "Granting ${SECRET_ROLE} on ${operator_secret} to ${operator_name} alone."
gcloud secrets add-iam-policy-binding "${operator_secret}" \
  --configuration=toolshed --quiet --project="${project}" \
  --member="serviceAccount:${operator_account}" \
  --role="${SECRET_ROLE}" > /dev/null

# Every deploy points both jobs at the image it just deployed
# (update-job-images.sh), so a job never waits on an image the cleanup policy
# has deleted. Updating a job's image means acting as the identity the job runs
# as, so the deployer of this environment may act as the operator account.
deployer_account="github-deployer-${environment}@${project}.iam.gserviceaccount.com"
echo "Letting ${deployer_account} act as ${operator_name}, so a deploy can update the job's image."
gcloud iam service-accounts add-iam-policy-binding "${operator_account}"   --configuration=toolshed --quiet --project="${project}"   --member="serviceAccount:${deployer_account}"   --role="roles/iam.serviceAccountUser" > /dev/null

echo "Deploying ${anonymise_job}."
gcloud run jobs deploy "${anonymise_job}" \
  --configuration=toolshed --quiet --project="${project}" \
  --region="${REGION}" \
  --image="${image}" \
  --service-account="${runtime_account}" \
  --command=python \
  --args=-m,app.jobs.anonymise_customers \
  --set-secrets="DATABASE_URL=${application_secret}:latest" \
  --tasks=1 \
  --max-retries="${JOB_MAX_RETRIES}" \
  --task-timeout="${JOB_TASK_TIMEOUT}" \
  --cpu="${JOB_CPU}" \
  --memory="${JOB_MEMORY}" \
  --labels="environment=${environment},purpose=anonymise-customers" > /dev/null

echo "Deploying ${prune_job}."
gcloud run jobs deploy "${prune_job}" \
  --configuration=toolshed --quiet --project="${project}" \
  --region="${REGION}" \
  --image="${image}" \
  --service-account="${operator_account}" \
  --command=python \
  --args=-m,app.jobs.prune_refresh_sessions \
  --set-secrets="OPERATOR_DATABASE_URL=${operator_secret}:latest" \
  --tasks=1 \
  --max-retries="${JOB_MAX_RETRIES}" \
  --task-timeout="${JOB_TASK_TIMEOUT}" \
  --cpu="${JOB_CPU}" \
  --memory="${JOB_MEMORY}" \
  --labels="environment=${environment},purpose=prune-sessions" > /dev/null

for job in "${anonymise_job}" "${prune_job}"; do
  echo "Granting ${INVOKER_ROLE} on ${job} to ${scheduler_name}."
  gcloud run jobs add-iam-policy-binding "${job}" \
    --configuration=toolshed --quiet --project="${project}" \
    --region="${REGION}" \
    --member="serviceAccount:${scheduler_account}" \
    --role="${INVOKER_ROLE}" > /dev/null
done

# Creates the schedule of a job, or updates it when it exists. A schedule
# created with "paused" is paused straight after it is made.
ensure_schedule() {
  local job="$1" schedule="$2" first_state="$3"
  local uri="https://run.googleapis.com/v2/projects/${project}/locations/${REGION}/jobs/${job}:run"
  local verb="create"
  if gcloud scheduler jobs describe "${job}" \
    --configuration=toolshed --quiet --project="${project}" \
    --location="${REGION}" > /dev/null 2>&1; then
    verb="update"
  fi
  echo "Writing the schedule of ${job}, '${schedule}' in ${TIME_ZONE} (${verb})."
  gcloud scheduler jobs "${verb}" http "${job}" \
    --configuration=toolshed --quiet --project="${project}" \
    --location="${REGION}" \
    --schedule="${schedule}" \
    --time-zone="${TIME_ZONE}" \
    --uri="${uri}" \
    --http-method=POST \
    --oauth-service-account-email="${scheduler_account}" > /dev/null
  if [ "${verb}" = "create" ] && [ "${first_state}" = "paused" ]; then
    echo "Pausing the new schedule of ${job} until its report has been read."
    gcloud scheduler jobs pause "${job}" \
      --configuration=toolshed --quiet --project="${project}" \
      --location="${REGION}" > /dev/null
  fi
}

ensure_schedule "${anonymise_job}" "${ANONYMISE_SCHEDULE}" paused
ensure_schedule "${prune_job}" "${PRUNE_SCHEDULE}" enabled

echo "Done. Run ${anonymise_job} once with --report and read its log before resuming its schedule."
