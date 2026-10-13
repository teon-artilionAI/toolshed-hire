#!/usr/bin/env bash
#
# Let the frontend's /api function, and nothing else on the internet, call the
# API of one environment (C-02, #96).
#
#   bash infra/scripts/create-edge-identity.sh <project> <environment> <vercel-team> <vercel-project>
#
#   project         the Google Cloud project of the environment
#   environment     staging or prod, the suffix the service and accounts carry
#   vercel-team     the slug of the Vercel team, whose OIDC issuer is trusted
#   vercel-project  the name of the Vercel project that serves this environment
#
# What it sets up, all of it keyless:
#
#   The Workload Identity pool "vercel" with a provider for the OIDC issuer of
#   the Vercel team. The provider admits only tokens that team issued for a
#   project whose name starts with toolshed-hire.
#
#   The service account toolshed-edge-<environment>, which holds
#   roles/run.invoker on toolshed-api-<environment> and nothing else. The
#   production deployments of the named Vercel project may mint ID tokens for
#   it, through roles/iam.workloadIdentityUser granted to that one subject.
#
#   roles/run.invoker on the same service for github-deployer-<environment>,
#   so the deploy workflow can smoke test a revision on the service's own
#   address once the service requires IAM.
#
# None of this changes who can call the service yet. The service keeps its
# public grant until it is deployed with API_ACCESS=iam, which removes it.
# Run this first, then set the two GitHub variables it prints, then deploy.
#
# The script can be run again at any time. What exists is left as it is, and
# the provider is updated to the settings written here.
#
# Every gcloud command carries --configuration=toolshed, so the account comes
# from that named configuration and never from whichever one happens to be
# active, and every command names the project it was given.

set -euo pipefail

POOL="vercel"
POOL_LOCATION="global"
REGION="europe-west2"
# A project that belongs to another product and must never be changed from here.
FORBIDDEN_PROJECT="fred-ai-prod-480815"
REQUIRED_SERVICES=(sts.googleapis.com iamcredentials.googleapis.com iam.googleapis.com run.googleapis.com)
INVOKER_ROLE="roles/run.invoker"
FEDERATION_ROLE="roles/iam.workloadIdentityUser"
# Only production deployments of the Vercel project serve the environment.
VERCEL_ENVIRONMENT="production"
PROJECT_NAME_PREFIX="toolshed-hire"

usage() {
  echo "Usage: bash infra/scripts/create-edge-identity.sh <project> <environment> <vercel-team> <vercel-project>" >&2
  echo "The environment is staging or prod." >&2
}

if [ "$#" -ne 4 ]; then
  usage
  exit 2
fi

project="$1"
environment="$2"
vercel_team="$3"
vercel_project="$4"

if [ "${project}" = "${FORBIDDEN_PROJECT}" ]; then
  echo "Refusing to touch ${FORBIDDEN_PROJECT}. It belongs to another product. Pass the Toolshed Hire project." >&2
  exit 1
fi

case "${environment}" in
  staging | prod) ;;
  *)
    echo "The environment must be staging or prod, not '${environment}'." >&2
    usage
    exit 2
    ;;
esac

if ! [[ "${vercel_team}" =~ ^[a-z0-9-]+$ ]] || ! [[ "${vercel_project}" =~ ^${PROJECT_NAME_PREFIX}[a-z0-9-]*$ ]]; then
  echo "The Vercel team must be a slug, and the Vercel project a name that starts with ${PROJECT_NAME_PREFIX}." >&2
  exit 2
fi

if ! gcloud config configurations describe toolshed \
  --configuration=toolshed > /dev/null 2>&1; then
  echo "There is no gcloud configuration named toolshed. Create it with 'gcloud config configurations create toolshed' and sign in." >&2
  exit 1
fi

service="toolshed-api-${environment}"
edge_name="toolshed-edge-${environment}"
edge_account="${edge_name}@${project}.iam.gserviceaccount.com"
deployer_account="github-deployer-${environment}@${project}.iam.gserviceaccount.com"
provider="vercel-${vercel_team}"
issuer="https://oidc.vercel.com/${vercel_team}"
audience="https://vercel.com/${vercel_team}"
condition="assertion.owner == '${vercel_team}' && assertion.project.startsWith('${PROJECT_NAME_PREFIX}')"
mapping="google.subject=assertion.sub,attribute.project=assertion.project,attribute.environment=assertion.environment"
subject="owner:${vercel_team}:project:${vercel_project}:environment:${VERCEL_ENVIRONMENT}"

echo "Project ${project}, environment ${environment}, Vercel project ${vercel_project} of team ${vercel_team}."

echo "Enabling ${REQUIRED_SERVICES[*]} where they are not on already."
gcloud services enable "${REQUIRED_SERVICES[@]}" \
  --configuration=toolshed --quiet --project="${project}" > /dev/null

project_number="$(gcloud projects describe "${project}" \
  --configuration=toolshed --format="value(projectNumber)")"

if gcloud iam workload-identity-pools describe "${POOL}" \
  --configuration=toolshed --quiet --project="${project}" --location="${POOL_LOCATION}" > /dev/null 2>&1; then
  echo "The pool ${POOL} exists already."
else
  echo "Creating the pool ${POOL}."
  gcloud iam workload-identity-pools create "${POOL}" \
    --configuration=toolshed --quiet --project="${project}" --location="${POOL_LOCATION}" \
    --display-name="Vercel" --description="Vercel functions of team ${vercel_team}" > /dev/null
fi

provider_verb="create-oidc"
if gcloud iam workload-identity-pools providers describe "${provider}" \
  --configuration=toolshed --quiet --project="${project}" --location="${POOL_LOCATION}" \
  --workload-identity-pool="${POOL}" > /dev/null 2>&1; then
  provider_verb="update-oidc"
fi
echo "Writing the provider ${provider} (${provider_verb})."
gcloud iam workload-identity-pools providers "${provider_verb}" "${provider}" \
  --configuration=toolshed --quiet --project="${project}" --location="${POOL_LOCATION}" \
  --workload-identity-pool="${POOL}" \
  --issuer-uri="${issuer}" \
  --allowed-audiences="${audience}" \
  --attribute-mapping="${mapping}" \
  --attribute-condition="${condition}" > /dev/null

if gcloud iam service-accounts describe "${edge_account}" \
  --configuration=toolshed --quiet --project="${project}" > /dev/null 2>&1; then
  echo "The service account ${edge_name} exists already."
else
  echo "Creating the service account ${edge_name}."
  gcloud iam service-accounts create "${edge_name}" \
    --configuration=toolshed --quiet --project="${project}" \
    --display-name="Vercel function that invokes ${service}" > /dev/null
fi

for member in "serviceAccount:${edge_account}" "serviceAccount:${deployer_account}"; do
  echo "Granting ${INVOKER_ROLE} on ${service} to ${member#serviceAccount:}."
  gcloud run services add-iam-policy-binding "${service}" \
    --configuration=toolshed --quiet --project="${project}" --region="${REGION}" \
    --member="${member}" --role="${INVOKER_ROLE}" > /dev/null
done

echo "Letting the ${VERCEL_ENVIRONMENT} deployments of ${vercel_project} act as ${edge_name}."
gcloud iam service-accounts add-iam-policy-binding "${edge_account}" \
  --configuration=toolshed --quiet --project="${project}" \
  --role="${FEDERATION_ROLE}" \
  --member="principal://iam.googleapis.com/projects/${project_number}/locations/${POOL_LOCATION}/workloadIdentityPools/${POOL}/subject/${subject}" > /dev/null

echo "Done. Set these variables on the GitHub environment, then deploy with API_ACCESS=iam and API_ROUTE=function:"
echo "  GCP_WORKLOAD_AUDIENCE=//iam.googleapis.com/projects/${project_number}/locations/${POOL_LOCATION}/workloadIdentityPools/${POOL}/providers/${provider}"
echo "  GCP_INVOKER_ACCOUNT=${edge_account}"
