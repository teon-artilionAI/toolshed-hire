#!/usr/bin/env bash
#
# Create the private bucket damage photographs are kept in, and let the API's
# runtime service account use it (#83).
#
#   bash infra/scripts/create-photo-bucket.sh <project> <environment> <bucket> <runtime-account>
#
#   project          the Google Cloud project of the environment
#   environment      staging or production
#   bucket           the name of the bucket, which PHOTO_BUCKET is then set to
#   runtime-account  the address of the Cloud Run runtime service account
#
# The bucket is in europe-west2 (London), with uniform bucket-level access and
# public access prevention enforced, so no object can ever be made public and
# no object carries an access list of its own. A lifecycle rule deletes each
# photograph 1,835 days after it was stored, which is the five year retention
# period and a few days over. The runtime account is granted object create and
# object read on this bucket alone, and nothing on the project. It is also
# granted Service Account Token Creator on itself, which lets it sign the five
# minute download links through the IAM signBlob call, because a Cloud Run
# instance holds no private key to sign with.
#
# The script can be run again at any time. A bucket that exists already has the
# same settings applied again, and a grant that exists already is left as it is.
# It refuses a bucket that exists in another location, because moving one means
# copying every photograph, which is a decision and not a retry.
#
# Every gcloud command carries --configuration=toolshed, so the project and the
# account come from that named configuration and never from whichever one
# happens to be active. The script prints the names it was given and what it
# did, and nothing else. No key is created and no bucket name is committed.

set -euo pipefail

LOCATION="europe-west2"
STORAGE_CLASS="STANDARD"
RETENTION_DAYS=1835
PURPOSE_LABEL="damage-photos"
# A project that belongs to another product and must never be changed from here.
FORBIDDEN_PROJECT="fred-ai-prod-480815"
REQUIRED_SERVICES=(storage.googleapis.com iamcredentials.googleapis.com)
OBJECT_ROLES=(roles/storage.objectCreator roles/storage.objectViewer)
SIGNING_ROLE="roles/iam.serviceAccountTokenCreator"

usage() {
  echo "Usage: bash infra/scripts/create-photo-bucket.sh <project> <environment> <bucket> <runtime-account>" >&2
  echo "The environment is staging or production." >&2
}

if [ "$#" -ne 4 ]; then
  usage
  exit 2
fi

project="$1"
environment="$2"
bucket="$3"
runtime_account="$4"

if [ "${project}" = "${FORBIDDEN_PROJECT}" ]; then
  echo "Refusing to touch ${FORBIDDEN_PROJECT}. It belongs to another product. Pass the Toolshed Hire project." >&2
  exit 1
fi

case "${environment}" in
  staging | production) ;;
  *)
    echo "The environment must be staging or production, not '${environment}'." >&2
    usage
    exit 2
    ;;
esac

# The rules Cloud Storage applies to a bucket name, checked here so a typing
# mistake stops the script before anything is created.
if ! [[ "${bucket}" =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]]; then
  echo "'${bucket}' is not a valid bucket name. Use 3 to 63 lower case letters, digits, dashes, underscores and dots." >&2
  exit 2
fi

if ! [[ "${runtime_account}" =~ ^[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com$ ]]; then
  echo "'${runtime_account}' is not the address of a service account." >&2
  exit 2
fi

# The named configuration has to exist. Without it gcloud would fall back to
# nothing at all, and the error it gives does not say why.
if ! gcloud config configurations describe toolshed \
  --configuration=toolshed > /dev/null 2>&1; then
  echo "There is no gcloud configuration named toolshed. Create it with 'gcloud config configurations create toolshed' and sign in." >&2
  exit 1
fi

lifecycle_file="$(mktemp)"
trap 'rm -f "${lifecycle_file}"' EXIT
cat > "${lifecycle_file}" <<EOF
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": ${RETENTION_DAYS}}}]}
EOF

echo "Project ${project}, environment ${environment}, bucket ${bucket}, location ${LOCATION}."

echo "Enabling ${REQUIRED_SERVICES[*]} where they are not on already."
gcloud services enable "${REQUIRED_SERVICES[@]}" --project="${project}" --configuration=toolshed --quiet > /dev/null

# A bucket that cannot be described is taken to be missing and is created. When
# the describe failed for another reason, missing permission for example, the
# create fails too and stops the script with gcloud's own message.
existing_location="$(gcloud storage buckets describe "gs://${bucket}" \
  --configuration=toolshed --quiet \
  --project="${project}" --format="value(location)" 2> /dev/null || true)"

if [ -z "${existing_location}" ]; then
  echo "Creating the bucket."
  gcloud storage buckets create "gs://${bucket}" \
    --configuration=toolshed --quiet \
    --project="${project}" \
    --location="${LOCATION}" \
    --default-storage-class="${STORAGE_CLASS}" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --lifecycle-file="${lifecycle_file}" > /dev/null
else
  # The service reports a region in capitals, for example EUROPE-WEST2.
  if [ "$(echo "${existing_location}" | tr '[:upper:]' '[:lower:]')" != "${LOCATION}" ]; then
    echo "The bucket exists in ${existing_location}, not ${LOCATION}. Moving it means copying every photograph, so nothing was changed." >&2
    exit 1
  fi
  echo "The bucket exists already in ${LOCATION}."
fi

echo "Applying uniform access, public access prevention, the ${RETENTION_DAYS} day lifecycle rule and the labels."
gcloud storage buckets update "gs://${bucket}" \
  --configuration=toolshed --quiet \
  --project="${project}" \
  --uniform-bucket-level-access \
  --public-access-prevention \
  --lifecycle-file="${lifecycle_file}" \
  --update-labels="environment=${environment},purpose=${PURPOSE_LABEL}" > /dev/null

for role in "${OBJECT_ROLES[@]}"; do
  echo "Granting ${role} on this bucket to the runtime account."
  gcloud storage buckets add-iam-policy-binding "gs://${bucket}" \
    --configuration=toolshed --quiet \
    --project="${project}" \
    --member="serviceAccount:${runtime_account}" \
    --role="${role}" > /dev/null
done

echo "Granting ${SIGNING_ROLE} to the runtime account on itself, so it can sign download links."
gcloud iam service-accounts add-iam-policy-binding "${runtime_account}" \
  --configuration=toolshed --quiet \
  --project="${project}" \
  --member="serviceAccount:${runtime_account}" \
  --role="${SIGNING_ROLE}" > /dev/null

echo "Done. Set PHOTO_BUCKET to ${bucket} for the ${environment} service."
