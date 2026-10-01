#!/usr/bin/env bash
#
# Check that every value a deployment needs is present, and fail if one is not.
#
# The first version of this script reported a missing value as a notice and let
# the run go green, because the cloud accounts did not exist yet and a
# permanently red pipeline helps nobody. They exist now. A deployment that
# skips itself and reports success is worse than one that fails, so a missing
# value stops the run and names what is missing.
#
# The values arrive as environment variables set by the calling workflow step.
# Only their presence is checked. Nothing here prints a value.

set -euo pipefail

REQUIRED_VARIABLES=(
  WORKLOAD_IDENTITY_PROVIDER
  DEPLOY_SERVICE_ACCOUNT
  PROJECT_ID
  REGION
  ARTIFACT_REGISTRY_REPOSITORY
  SERVICE_NAME
  RUNTIME_SERVICE_ACCOUNT
  DATABASE_URL_SECRET
  DATABASE_MIGRATION_URL_SECRET
  JWT_SECRET_NAME
  RESEND_API_KEY_SECRET
  EMAIL_ALLOWED_RECIPIENT
  FRONTEND_ORIGIN
  VERCEL_TOKEN
  VERCEL_ORG_ID
  VERCEL_PROJECT_ID
  SEED_PASSWORD
)

missing=()
for name in "${REQUIRED_VARIABLES[@]}"; do
  if [ -z "${!name:-}" ]; then
    missing+=("${name}")
  fi
done

if [ "${#missing[@]}" -gt 0 ]; then
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      echo "### Deployment stopped"
      echo
      echo "These configuration values are missing for this environment:"
      echo
      for name in "${missing[@]}"; do
        echo "- \`${name}\`"
      done
      echo
      echo "\`infra/SETUP.md\` lists where each one is set."
    } >> "${GITHUB_STEP_SUMMARY}"
  fi
  echo "::error title=Deployment configuration incomplete::Missing: ${missing[*]}"
  exit 1
fi

echo "All ${#REQUIRED_VARIABLES[@]} required configuration values are present."
