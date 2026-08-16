# Standing up Toolshed Hire from nothing

Every command needed to go from an empty machine to a deployed system. Follow
it in order. Later steps consume values produced by earlier ones.

Steps that cost money or need a payment card are marked **[CARD]**. Nothing
here leaves a free allowance during build, but one account refuses to exist
without a card and one plan has to change at go-live.

Three companion files carry the parts that would otherwise bury this one:

- `WORKLOAD-IDENTITY-FEDERATION.md`, step 7 in full with its failure modes.
- `VERCEL-REWRITE.md`, why the single origin rewrite exists and how it fails.
- `OPERATIONS.md`, local development, costs, rollback and tearing it down.

## 0. Tools and accounts

Install and sign in. The accounts needed are Google Cloud, GitHub, Neon and
Vercel.

```bash
gcloud --version          # Google Cloud CLI
gh --version              # GitHub CLI
vercel --version          # Vercel CLI
docker --version          # for building the image locally
psql --version            # optional, useful for poking at the database
```

Set the values this guide reuses and keep the shell open.

```bash
export PROJECT_ID="toolshed-hire-prod"
export REGION="europe-west1"
export AR_REPOSITORY="toolshed-hire"
export SERVICE_NAME="toolshed-hire-api"
export GITHUB_REPOSITORY="OWNER/REPO"        # for example teon-artilionAI/ToolshedHire
export GITHUB_OWNER="${GITHUB_REPOSITORY%%/*}"
export POOL_ID="github"
export PROVIDER_ID="github-actions"
export DEPLOY_SA="github-deployer"
export RUNTIME_SA="toolshed-hire-api"
```

`europe-west1` is used because Neon's free plan has no African region and the
API makes several database round trips per browser request. Paying the Cape
Town distance once on the browser leg beats paying it per query, which is the
trade-off recorded in the Deployment Plan.

## 1. Google Cloud project [CARD]

A billing account is required even when everything stays inside the free
allowance. Google will not enable Cloud Run without one and it verifies a card.
Nothing is charged inside the allowance, with the one exception in section 11.

```bash
gcloud auth login
gcloud projects create "${PROJECT_ID}" --name="Toolshed Hire"
gcloud config set project "${PROJECT_ID}"

gcloud billing accounts list
gcloud billing projects link "${PROJECT_ID}" \
  --billing-account="BILLING_ACCOUNT_ID"

# Capture the project NUMBER. Workload Identity Federation uses the number and
# not the id, and using the id there is a common and confusing failure.
export PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" \
  --format='value(projectNumber)')"
echo "Project number: ${PROJECT_NUMBER}"
```

**Set a budget alert now.** It costs nothing and is the only thing standing
between a misconfiguration and a surprise.

```bash
gcloud billing budgets create \
  --billing-account="BILLING_ACCOUNT_ID" \
  --display-name="Toolshed Hire guard rail" \
  --budget-amount=10USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9
```

## 2. Enable the APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com \
  logging.googleapis.com \
  --project="${PROJECT_ID}"
```

`iamcredentials` and `sts` are the two people forget. Without them the deploy
workflow's token exchange fails with a message that mentions neither.

## 3. Artifact Registry

```bash
gcloud artifacts repositories create "${AR_REPOSITORY}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="Toolshed Hire container images" \
  --project="${PROJECT_ID}"
```

The free allowance is 0.5 GB and each API image is roughly 200 MB, so three
fill it. Add a cleanup policy so old digests do not accumulate:

```bash
cat > /tmp/cleanup-policy.json <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"},
   "mostRecentVersions": {"keepCount": 3}},
  {"name": "delete-old", "action": {"type": "Delete"},
   "condition": {"olderThan": "30d"}}
]
JSON

gcloud artifacts repositories set-cleanup-policies "${AR_REPOSITORY}" \
  --location="${REGION}" --policy=/tmp/cleanup-policy.json \
  --project="${PROJECT_ID}"
```

## 4. Two service accounts, doing two different jobs

Keeping these separate is the point. The deployer creates revisions and cannot
read application data. The runtime identity reads its own secrets and cannot
deploy.

```bash
gcloud iam service-accounts create "${DEPLOY_SA}" \
  --display-name="GitHub Actions deployer" --project="${PROJECT_ID}"

gcloud iam service-accounts create "${RUNTIME_SA}" \
  --display-name="Toolshed Hire API runtime" --project="${PROJECT_ID}"

export DEPLOY_SA_EMAIL="${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
export RUNTIME_SA_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
```

## 5. Neon, and the two connection strings

The free plan needs no card. Create the project at
<https://console.neon.tech>, choosing a **European region**, for example
`aws-eu-central-1`, so it sits beside `europe-west1`.

Copy **two different connection strings** from the Connection Details panel.
They are not interchangeable, and the wrong one fails in ways that look like
flaky networking.

| Which | Host contains | Used by | Why |
|---|---|---|---|
| Pooled | `-pooler` | The running API | Cloud Run scales to several instances and the pooler keeps the total connection count inside the plan allowance |
| Direct | no `-pooler` | Alembic migrations | The pooler runs in transaction pooling mode and holds no session state, which breaks advisory locks, `CREATE EXTENSION` and some transactional DDL |

Confirm the extension the whole system depends on is permitted:

```bash
psql "DIRECT_CONNECTION_STRING" \
  -c "CREATE EXTENSION IF NOT EXISTS btree_gist;" \
  -c "SELECT extname FROM pg_extension WHERE extname = 'btree_gist';"
```

The migration creates it too. Running it here confirms the plan allows it
before you find out mid deployment. Then rewrite both strings into SQLAlchemy
form: replace the leading `postgresql://` with `postgresql+psycopg://` and keep
`?sslmode=require`.

## 6. Secret Manager

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))" | tr -d '\n' \
  | gcloud secrets create toolshed-jwt-secret \
      --data-file=- --project="${PROJECT_ID}"

printf '%s' 'POOLED_SQLALCHEMY_URL' \
  | gcloud secrets create toolshed-database-url \
      --data-file=- --project="${PROJECT_ID}"

printf '%s' 'DIRECT_SQLALCHEMY_URL' \
  | gcloud secrets create toolshed-database-migration-url \
      --data-file=- --project="${PROJECT_ID}"
```

`printf` rather than `echo`, because `echo` appends a newline and a connection
string with a trailing newline fails to parse in a way that reads as a bad
password. Never reuse a signing key across environments. Now grant read access,
narrowly.

```bash
# The runtime identity reads only what the running service needs: the pooled
# connection and the signing key. It is deliberately not granted the direct
# connection string.
for secret in toolshed-database-url toolshed-jwt-secret; do
  gcloud secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" --project="${PROJECT_ID}"
done

# The deployer reads only the direct connection string, and only to run
# Alembic. It never sees the signing key.
gcloud secrets add-iam-policy-binding toolshed-database-migration-url \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" --project="${PROJECT_ID}"
```

## 7. Workload Identity Federation

This is the step that costs a day when it goes wrong, because every mistake
produces the same opaque credentials error. It has five mandatory pieces: a
pool, an OIDC provider, an attribute mapping, an attribute condition that
Google will not let you omit, and three IAM bindings.

**The commands, the reasoning and the failure-to-cause table are in
`WORKLOAD-IDENTITY-FEDERATION.md`.** Work through that file now, then come
back here with the provider resource name it prints at the end.

## 8. GitHub secrets and variables

Two secrets and eight variables. Neither secret is a credential in the usual
sense, but both are stored as secrets so nothing outside the repository can
read the identity of the deployment target.

```bash
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "${GITHUB_REPOSITORY}" \
  --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"
gh secret set GCP_DEPLOY_SERVICE_ACCOUNT --repo "${GITHUB_REPOSITORY}" \
  --body "${DEPLOY_SA_EMAIL}"

gh variable set GCP_PROJECT_ID --repo "${GITHUB_REPOSITORY}" --body "${PROJECT_ID}"
gh variable set GCP_REGION --repo "${GITHUB_REPOSITORY}" --body "${REGION}"
gh variable set GCP_ARTIFACT_REGISTRY_REPOSITORY --repo "${GITHUB_REPOSITORY}" --body "${AR_REPOSITORY}"
gh variable set CLOUD_RUN_SERVICE --repo "${GITHUB_REPOSITORY}" --body "${SERVICE_NAME}"
gh variable set CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT --repo "${GITHUB_REPOSITORY}" --body "${RUNTIME_SA_EMAIL}"
gh variable set DATABASE_URL_SECRET_NAME --repo "${GITHUB_REPOSITORY}" --body "toolshed-database-url"
gh variable set DATABASE_MIGRATION_URL_SECRET_NAME --repo "${GITHUB_REPOSITORY}" --body "toolshed-database-migration-url"
gh variable set JWT_SECRET_NAME --repo "${GITHUB_REPOSITORY}" --body "toolshed-jwt-secret"
```

Until all ten exist the deploy workflow skips itself and posts a notice naming
what is missing, so the repository is never red for want of a cloud account.
That guard is the `preflight` job in `.github/workflows/deploy.yml`.

Create the `production` environment in the repository settings and set it to
require a manual approval. That is the deliberate pause before a release, and
the DevOps section describes it as exactly that rather than as peer review.

## 9. First deployment

The workflow builds the image, pushes it by digest, applies migrations from the
runner, deploys the revision, then smoke tests `/api/health` and fails the run
if it does not answer 200 with `"status": "healthy"`.

```bash
git push origin main
gh run watch

# Read back the service URL, which step 10 needs.
gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" \
  --format='value(status.url)'
```

## 10. Vercel and the single origin rewrite [CARD at go-live]

Hobby is free and is what the project uses during build. **Hobby forbids
commercial use**, so the plan moves to Pro at go-live, currently USD 20 per
member per month.

```bash
cd frontend
vercel link
vercel env add CLOUD_RUN_API_ORIGIN production
# Paste the Cloud Run URL from step 9, with no trailing slash, for example
#   https://toolshed-hire-api-abc123-ew.a.run.app
vercel env add CLOUD_RUN_API_ORIGIN preview      # optional, same value
vercel deploy --prod
```

**Then verify it**, because a broken rewrite is silent until a user hits it:

```bash
curl -i https://YOUR-VERCEL-DOMAIN/api/health
```

A 200 with the same body as the Cloud Run URL means the single origin is
working. Anything else, and what each failure means, is in
`VERCEL-REWRITE.md`, which also carries the explanation of why the rewrite
exists at all. That file is where the reasoning lives because `vercel.json` is
JSON, which permits no comments.

## 11. What it costs

The claim that nothing costs money is false and is not made anywhere. Every
service runs inside a free allowance during build and demonstration. Two lines
leave it at go-live, the Vercel plan and European egress, and both are
quantified under "What actually costs money" in `OPERATIONS.md`.
