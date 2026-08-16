#!/usr/bin/env bash
#
# Deployment preflight guard.
#
# Reports whether every secret and variable the deploy workflow needs is
# present. The repository must not be permanently red because the cloud
# accounts do not exist yet, so a missing configuration is a skipped deployment
# with an explanatory notice, never a failed run.
#
# Reads its inputs from the environment, because two of them are secrets and
# passing a secret as a command line argument puts it in the process table.
# Only presence is ever tested and no value is ever echoed.
#
# Writes "configured=true" or "configured=false" to GITHUB_OUTPUT.
# Exits 0 either way. A non-zero exit here would defeat the entire purpose.

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
)

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is not set. This script runs inside a GitHub Actions step.}"
: "${GITHUB_STEP_SUMMARY:?GITHUB_STEP_SUMMARY is not set. This script runs inside a GitHub Actions step.}"

missing=()
for name in "${REQUIRED_VARIABLES[@]}"; do
  if [ -z "${!name:-}" ]; then
    missing+=("${name}")
  fi
done

if [ "${#missing[@]}" -gt 0 ]; then
  echo "configured=false" >> "${GITHUB_OUTPUT}"
  {
    echo "### Deployment skipped"
    echo
    echo "The Google Cloud configuration is not complete yet, so the deploy job"
    echo "was skipped rather than failed. Missing:"
    echo
    for name in "${missing[@]}"; do
      echo "- \`${name}\`"
    done
    echo
    echo "Follow \`infra/SETUP.md\`, then add them under Settings, Secrets and"
    echo "variables, Actions."
  } >> "${GITHUB_STEP_SUMMARY}"
  echo "::notice title=Deployment skipped::Missing configuration: ${missing[*]}"
  exit 0
fi

echo "configured=true" >> "${GITHUB_OUTPUT}"
echo "All ${#REQUIRED_VARIABLES[@]} required configuration values are present."
