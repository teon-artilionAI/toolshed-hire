#!/usr/bin/env bash
#
# Load the reference fleet and the demonstration accounts.
#
# The seed is idempotent on natural keys, so it runs on every deployment and
# only creates what is not there yet. It connects with the same direct
# connection string the migrations use, read from Secret Manager at run time.
#
# The customer accounts get their own password, because one customer login is
# published for demonstration and the staff and admin logins are not. Both
# passwords reach the seed through the environment and are never echoed.

set -euo pipefail

: "${DATABASE_MIGRATION_URL_SECRET:?DATABASE_MIGRATION_URL_SECRET is not set}"
: "${SEED_PASSWORD:?SEED_PASSWORD is not set}"
: "${SEED_CUSTOMER_PASSWORD:?SEED_CUSTOMER_PASSWORD is not set}"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

database_url="$(gcloud secrets versions access latest \
  --secret="${DATABASE_MIGRATION_URL_SECRET}")"
echo "::add-mask::${database_url}"

if [ -z "${database_url}" ]; then
  echo "::error title=Empty database URL::Secret ${DATABASE_MIGRATION_URL_SECRET} resolved to an empty value, so there is nothing to seed."
  exit 1
fi

cd "${REPOSITORY_ROOT}/backend"

# ENVIRONMENT is left unset on purpose, the same way the migration step leaves
# it. The seed needs a database connection and nothing else, and the deploy
# identity is deliberately not allowed to read the signing key that a
# production start-up check would ask for.
echo "Seeding the database."
DATABASE_URL="${database_url}" python seed.py
