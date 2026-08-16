#!/usr/bin/env bash
#
# Apply Alembic migrations to the deployed database, from the pipeline runner.
#
# Migrations deliberately do not run from the container start-up path. Several
# instances of one Cloud Run revision would race to apply the same migration, a
# slow migration would trip the start-up probe, and a failed migration would
# present as a service that will not boot instead of as a pipeline that failed.
# Running here means that when this fails, production is completely untouched.
#
# The connection string is read from Secret Manager at the moment it is needed
# and masked immediately, so GitHub holds no database credential at all and the
# value never reaches a log or the job environment.
#
# The DIRECT connection string is used, not the pooled one. Neon's pooler runs
# in transaction pooling mode and does not hold session state across
# statements, which breaks advisory locks, CREATE EXTENSION and some
# transactional DDL. The failures that produces look like flaky networking.
#
# Alembic reads settings.database_url, which comes from DATABASE_URL, so the
# direct string is exported under that name for the length of this command
# only. The running service keeps the pooled string, which is the value mounted
# into the Cloud Run revision.
#
# ENVIRONMENT is deliberately left unset, so the settings model resolves to
# development and applies its relaxed validation. Migrations are DDL and need
# no signing key, and claiming production here would mean fetching a second
# secret purely to satisfy a validator.
#
# Required environment:
#   DATABASE_MIGRATION_URL_SECRET   Secret Manager secret holding the direct URL

set -euo pipefail

: "${DATABASE_MIGRATION_URL_SECRET:?DATABASE_MIGRATION_URL_SECRET is not set}"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Reading the migration connection string from Secret Manager secret ${DATABASE_MIGRATION_URL_SECRET}"
migration_url="$(gcloud secrets versions access latest \
  --secret="${DATABASE_MIGRATION_URL_SECRET}")"

# Masked before anything else in this process can print it.
echo "::add-mask::${migration_url}"

if [ -z "${migration_url}" ]; then
  echo "::error title=Empty migration URL::Secret ${DATABASE_MIGRATION_URL_SECRET} resolved to an empty value. Alembic cannot run against an unknown database, and running it against a default would be worse. Check that the secret has an enabled version and that the deploy service account holds roles/secretmanager.secretAccessor on it."
  exit 1
fi

cd "${REPOSITORY_ROOT}/backend"

echo "Applying migrations to head."
DATABASE_URL="${migration_url}" alembic upgrade head

echo "Migrations applied. Current revision:"
DATABASE_URL="${migration_url}" alembic current
