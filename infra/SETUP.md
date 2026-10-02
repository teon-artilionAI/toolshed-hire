# Standing up Toolshed Hire from nothing

Every step I took to go from no cloud accounts to two environments, staging and
production. I follow it in order and keep one shell open, because later steps
use values that earlier steps produce. Steps that need a payment card are
marked **[CARD]**.

The repository is public. Every account specific value in these files is a
shell variable or an obvious placeholder such as `PROJECT_NUMBER`, and I keep
it that way whenever I edit them.

Three companion files carry the parts that would otherwise bury this one.
`WORKLOAD-IDENTITY-FEDERATION.md` is step 7 in full, with its failure modes.
`VERCEL-REWRITE.md` is step 8 in full, with the `/api` rewrite and how it
fails. `OPERATIONS.md` covers local development, what a deployment does and
how I check it, rollback, costs and tearing it all down.

## What exists at the end

| Piece | Staging | Production |
|---|---|---|
| GitHub environment | `staging`, from `develop` only | `production`, from `v*` tags, after my approval |
| Cloud Run service | `toolshed-api-staging` | `toolshed-api-prod` |
| Deployer identity | `github-deployer-staging` | `github-deployer-prod` |
| Runtime identity | `toolshed-api-run-staging` | `toolshed-api-run-prod` |
| Secrets | Four with the prefix `staging-` | Four with the prefix `prod-` |
| Neon branch | `staging` | `main` |
| Vercel project | `toolshed-hire-staging` | `toolshed-hire` |
| Public site | <https://toolshed-hire-staging.vercel.app> | <https://toolshed-hire.vercel.app> |

The two share one Google Cloud project, one Artifact Registry repository, one
Neon project and one federation pool. Everything that holds data or a
credential is separate. The cloud side uses the short name `prod` and the
GitHub environment is called `production`.

## 0. Tools and shell variables

I need accounts with Google Cloud, GitHub, Neon and Vercel, and `gcloud`, `gh`,
`docker` and Python 3.12 on my machine.

```bash
export PROJECT_ID="toolshed-hire"
export REGION="europe-west2"
export AR_REPOSITORY="toolshed"
export GITHUB_REPOSITORY="OWNER/REPO"
export BILLING_ACCOUNT_ID="BILLING_ACCOUNT_ID"   # listed in step 1
export POOL_ID="github"
export PROVIDER_ID="github-actions"

# The address of a service account in this project.
sa_email() { echo "${1}@${PROJECT_ID}.iam.gserviceaccount.com"; }
```

`europe-west2` is London. The database is in AWS London and the API makes
several database round trips for each request, so I put the API beside it.
London is a dearer Cloud Run price tier than Belgium. I made that trade on
purpose and record it here.

## 1. Google Cloud project and billing [CARD]

Google will not enable Cloud Run without a billing account, and a billing
account needs a card. What the free trial and the Free Tier cover is in the
costs section of `OPERATIONS.md`.

```bash
gcloud auth login
gcloud projects create "${PROJECT_ID}" --name="Toolshed Hire"
gcloud config set project "${PROJECT_ID}"
gcloud billing accounts list
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"
# Workload Identity Federation uses the project NUMBER and not the id.
export PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
```

## 2. APIs and the budget

```bash
gcloud services enable --project="${PROJECT_ID}" \
  run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudresourcemanager.googleapis.com logging.googleapis.com billingbudgets.googleapis.com
```

`iamcredentials` and `sts` are the two that are easy to forget. Without them
the token exchange in a deployment fails with a message that names neither.

The budget is 30 USD, scoped to this project, with alerts at 20, 50 and 100
percent. A budget only warns. It does not cap spending. The hard ceiling is the
instance cap on each Cloud Run service, which the workflows set.

```bash
gcloud billing budgets create \
  --billing-account="${BILLING_ACCOUNT_ID}" --display-name="Toolshed Hire" \
  --budget-amount=30USD --filter-projects="projects/${PROJECT_ID}" \
  --threshold-rule=percent=0.2 --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
```

## 3. Artifact Registry

One Docker repository, `toolshed`, holding one image, `api`. Both environments
push to it. The free allowance is 0.5 GB, so a cleanup policy keeps the three
most recent versions and deletes anything older than seven days.

```bash
gcloud artifacts repositories create "${AR_REPOSITORY}" \
  --repository-format=docker --location="${REGION}" \
  --description="Toolshed Hire container images" --project="${PROJECT_ID}"

cat > /tmp/cleanup-policy.json <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "7d"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "${AR_REPOSITORY}" \
  --location="${REGION}" --policy=/tmp/cleanup-policy.json --no-dry-run --project="${PROJECT_ID}"
```

## 4. Four service accounts and their roles

Each environment has its own deployer and its own runtime identity. A deployer
creates revisions and pushes images, and cannot read application data. A
runtime identity writes logs and reads its own secrets, and cannot deploy. A
deployer may run a revision as its own environment's runtime identity and as no
other. Nothing is shared, so staging can never read production's secrets.

```bash
for env_name in staging prod; do
  deployer="$(sa_email "github-deployer-${env_name}")"
  runtime="$(sa_email "toolshed-api-run-${env_name}")"
  gcloud iam service-accounts create "github-deployer-${env_name}" \
    --display-name="GitHub Actions deployer, ${env_name}" --project="${PROJECT_ID}"
  gcloud iam service-accounts create "toolshed-api-run-${env_name}" \
    --display-name="Toolshed Hire API runtime, ${env_name}" --project="${PROJECT_ID}"
  for role in roles/run.admin roles/artifactregistry.writer; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${deployer}" --role="${role}"
  done
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${runtime}" --role="roles/logging.logWriter"
  gcloud iam service-accounts add-iam-policy-binding "${runtime}" \
    --member="serviceAccount:${deployer}" --role="roles/iam.serviceAccountUser" --project="${PROJECT_ID}"
done
```

## 5. Neon

The free plan needs no card. I create one project in the Neon console, in AWS
`eu-west-2`, London, beside the API. I choose PostgreSQL 16 deliberately,
because the version cannot be changed after creation and the console may offer
a newer one by default. The hosted sign in service Neon offers stays off. This
system has its own.

The default branch `main` is production. I create the branch `staging` from it
while it is still empty and before any role is provisioned. That order is why
the two branches have different role passwords. The database on both is
`neondb`.

**The two roles.** `toolshed_migrate` runs the migrations and the seed.
`toolshed_app` is what the running API connects as. I create both in SQL with
`backend/scripts/provision_roles.py` and never in the Neon console. A role made
in the console joins `neon_superuser`, and it could then rewrite the audit
table. I run the script once on each branch, as the branch owner, from the
backend directory with the backend installed. `DATABASE_OWNER_URL` is the
owner's connection string for that branch, copied from the Neon console. Each
password is sixteen characters or more, which the script enforces, and differs
between the branches. The generator in step 6 gives a value that needs no
escaping inside a connection string. Running the script again is safe and sets
the passwords again, which is also how I rotate one.

```bash
cd backend
export DATABASE_OWNER_URL='OWNER_CONNECTION_STRING_FOR_THIS_BRANCH'
export APP_ROLE_PASSWORD='APP_ROLE_PASSWORD'
export MIGRATE_ROLE_PASSWORD='MIGRATE_ROLE_PASSWORD'
python scripts/provision_roles.py
```

**The two connection strings.** Each branch has its own endpoint, and I write
two strings for it in SQLAlchemy form. The pooled host is the endpoint id with
`-pooler` appended to its first label.

| Which | Role | Used by | Why |
|---|---|---|---|
| Pooled | `toolshed_app` | The running API | Cloud Run can run several instances and the pooler keeps the connection count inside the plan allowance |
| Direct | `toolshed_migrate` | Migrations and the seed, from the runner | The pooler holds no session state, which breaks advisory locks, `CREATE EXTENSION` and some transactional DDL |

```text
postgresql+psycopg://toolshed_app:APP_ROLE_PASSWORD@ENDPOINT_ID-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt&channel_binding=require
postgresql+psycopg://toolshed_migrate:MIGRATE_ROLE_PASSWORD@ENDPOINT_ID.eu-west-2.aws.neon.tech/neondb?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt&channel_binding=require
```

TLS is verified. I tried `sslrootcert=system` first and it failed with
"certificate verify failed: unable to get local issuer certificate", because
the libpq bundled in the psycopg binary wheel does not look in Debian's
certificate directory. Naming the bundle file works on the runner and in the
container, which are both Debian based. What I checked on staging once the
roles were in use is in `OPERATIONS.md`.

## 6. Secret Manager

Eight secrets, four for each environment, one version each. `ENV` is `staging`
or `prod`.

| Secret | Holds | Read by |
|---|---|---|
| `ENV-database-url` | The pooled string, as `toolshed_app` | The runtime identity |
| `ENV-jwt-secret` | The signing key | The runtime identity |
| `ENV-resend-api-key` | The key for the email provider | The runtime identity |
| `ENV-database-migration-url` | The direct string, as `toolshed_migrate` | The deployer |

The signing key goes straight from the generator into Secret Manager, so no
person ever sees it, and each environment gets its own. I run this block once
for `staging` and once for `prod`, each time with that environment's values.

```bash
env_name="staging"
python -c "import secrets; print(secrets.token_urlsafe(64), end='')" \
  | gcloud secrets create "${env_name}-jwt-secret" --data-file=- --project="${PROJECT_ID}"
printf '%s' 'POOLED_SQLALCHEMY_URL' \
  | gcloud secrets create "${env_name}-database-url" --data-file=- --project="${PROJECT_ID}"
printf '%s' 'DIRECT_SQLALCHEMY_URL' \
  | gcloud secrets create "${env_name}-database-migration-url" --data-file=- --project="${PROJECT_ID}"
printf '%s' 'RESEND_API_KEY' \
  | gcloud secrets create "${env_name}-resend-api-key" --data-file=- --project="${PROJECT_ID}"
```

I use `printf '%s'` and never `echo`. `echo` appends a newline, and a
connection string with a trailing newline fails in a way that reads as a wrong
password. Then I grant read access narrowly. The deployer reads the direct
string only, to run Alembic and the seed.

```bash
for env_name in staging prod; do
  for secret in database-url jwt-secret resend-api-key; do
    gcloud secrets add-iam-policy-binding "${env_name}-${secret}" \
      --member="serviceAccount:$(sa_email "toolshed-api-run-${env_name}")" \
      --role="roles/secretmanager.secretAccessor" --project="${PROJECT_ID}"
  done
  gcloud secrets add-iam-policy-binding "${env_name}-database-migration-url" \
    --member="serviceAccount:$(sa_email "github-deployer-${env_name}")" \
    --role="roles/secretmanager.secretAccessor" --project="${PROJECT_ID}"
done
```

## 7. Workload Identity Federation

No service account key exists anywhere. GitHub proves which job is running and
Google hands that job a short lived token for one deployer. The commands, the
reasoning and the failure table are in `WORKLOAD-IDENTITY-FEDERATION.md`. I
work through that file now and come back with `PROJECT_NUMBER` still set.

## 8. Vercel

Two projects on the Hobby plan, `toolshed-hire` for production and
`toolshed-hire-staging` for staging, with nothing connected to Git and
deployment protection switched off. How I set them up is at the top of
`VERCEL-REWRITE.md`. I come back with the team id, the two project ids and an
access token for the workflows.

## 9. GitHub environments, secrets and variables

I create two environments in the repository settings. `staging` accepts
deployments from the branch `develop` only. `production` has one required
reviewer, which is me with self review allowed, and accepts deployments from
tags matching `v*` only.

Every value belongs to an environment and none to the repository. I run this
block twice, with the first three lines changed for the second pass.

```bash
export GH_ENV="staging" CLOUD_ENV="staging"      # then "production" and "prod"
export FRONTEND_ORIGIN="https://toolshed-hire-staging.vercel.app"   # then https://toolshed-hire.vercel.app
export VERCEL_PROJECT_ID="VERCEL_PROJECT_ID"     # that environment's project
export VERCEL_TEAM_ID="VERCEL_TEAM_ID"
gh_var() { gh variable set "$1" --env "${GH_ENV}" --repo "${GITHUB_REPOSITORY}" --body "$2"; }
gh_secret() { gh secret set "$1" --env "${GH_ENV}" --repo "${GITHUB_REPOSITORY}" --body "$2"; }

gh_var GCP_PROJECT_ID "${PROJECT_ID}"
gh_var GCP_REGION "${REGION}"
gh_var GCP_ARTIFACT_REGISTRY_REPOSITORY "${AR_REPOSITORY}"
gh_var CLOUD_RUN_SERVICE "toolshed-api-${CLOUD_ENV}"
gh_var CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT "$(sa_email "toolshed-api-run-${CLOUD_ENV}")"
gh_var DATABASE_URL_SECRET_NAME "${CLOUD_ENV}-database-url"
gh_var DATABASE_MIGRATION_URL_SECRET_NAME "${CLOUD_ENV}-database-migration-url"
gh_var JWT_SECRET_NAME "${CLOUD_ENV}-jwt-secret"
gh_var RESEND_API_KEY_SECRET_NAME "${CLOUD_ENV}-resend-api-key"
gh_var FRONTEND_ORIGIN "${FRONTEND_ORIGIN}"
gh_var VERCEL_ORG_ID "${VERCEL_TEAM_ID}"
gh_var VERCEL_PROJECT_ID "${VERCEL_PROJECT_ID}"

gh_secret GCP_DEPLOY_SERVICE_ACCOUNT "$(sa_email "github-deployer-${CLOUD_ENV}")"
gh_secret GCP_WORKLOAD_IDENTITY_PROVIDER \
  "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

# These four are typed at the prompt, so they never sit in shell history.
for name in VERCEL_TOKEN EMAIL_ALLOWED_RECIPIENT SEED_PASSWORD SEED_CUSTOMER_PASSWORD; do
  gh secret set "${name}" --env "${GH_ENV}" --repo "${GITHUB_REPOSITORY}"
done
```

`FRONTEND_ORIGIN` has no trailing slash. `SEED_PASSWORD` goes to the staff and
admin accounts the seed creates and `SEED_CUSTOMER_PASSWORD` to the customer
accounts, so one customer login can be published without exposing the others.
GitHub holds no database credential. The workflows read the connection string
from Secret Manager when they need it.

A missing value fails the run and names what is missing. Nothing is passed over
quietly. `infra/scripts/check-deploy-config.sh` checks all eighteen values
straight after the checkout in both workflows.

## 10. First deployment

A merge into `develop` starts `.github/workflows/deploy-staging.yml`, and that
first run creates the Cloud Run service. Nobody creates it by hand. Production
is deployed by `.github/workflows/deploy-production.yml`, and only by a release
tag of the form `vX.Y.Z` on `main`, as `CONTRIBUTING.md` describes. The first
release creates `toolshed-api-prod` the same way.

What both workflows do, how the first staging deployment went on 2 October
2026, and what all of this costs are in `OPERATIONS.md`.
