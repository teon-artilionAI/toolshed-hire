# Running and operating Toolshed Hire

Local development, checking a deployment, rollback, costs and tearing it down.
`SETUP.md` is what I follow once. This is what I come back to.

The commands below reuse `PROJECT_ID`, `REGION` and `AR_REPOSITORY` from step 0
of `SETUP.md`.

## Local development

PostgreSQL 16 locally, in CI and on Neon. Testing against a different major
version from production is how a constraint that works everywhere except
production gets shipped.

```bash
docker run --name tsh-pg -e POSTGRES_USER=toolshed -e POSTGRES_PASSWORD=toolshed \
  -e POSTGRES_DB=toolshed -p 5432:5432 -d postgres:16
```

```bash
cd backend
cp .env.example .env      # .env is git ignored and never committed
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\Activate.ps1 in PowerShell
pip install --editable ".[dev]"
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm ci
npm run dev
```

The page is on <http://localhost:5173> and the API on <http://localhost:8000>.
The Vite dev server proxies `/api` to the API, so the browser sees one origin
locally exactly as it does through the Vercel rewrite when deployed.

A local database with one owner needs neither of the two database roles.
Migration 0002 finds no `toolshed_app`, leaves the grants out, says so in the
log and still succeeds.

The tests marked `postgres` truncate every table. They get their own disposable
database from `docker-compose.yml` and never the seeded one above.
`backend/README.md` shows how I run the two side by side.

## Running the checks the pipeline runs

I run these before I push. They are the commands the fast checks run on every
push.

```bash
cd backend
ruff check .
mypy app
mypy seed.py seeding seed_data scripts
lint-imports
pytest tests -m "not postgres"

cd ../frontend
npm run lint
npm run typecheck
npm run test
```

A pull request into `develop` or `main` adds the slower checks. They are the
migrations from an empty database, the whole test suite against PostgreSQL with
the coverage floor, `pip-audit`, `npm audit --audit-level=high`,
`npm run build` and `npm run test:e2e`.

## Building the image the way the pipeline builds it

```bash
docker build --file backend/Dockerfile --tag toolshed-api:local backend

docker run --rm -p 8080:8080 \
  -e ENVIRONMENT=development \
  -e DATABASE_URL="postgresql+psycopg://toolshed:toolshed@host.docker.internal:5432/toolshed" \
  toolshed-api:local

curl -s localhost:8080/api/health
```

The container listens on 8080, which is what Cloud Run expects.
`host.docker.internal` is how it reaches a database running on the host. The
Dockerfile records the measured size, about 76 MB compressed, which is what the
registry stores and what a cold start pulls.

## What a deployment does

| | Staging | Production |
|---|---|---|
| Workflow | `deploy-staging.yml` | `deploy-production.yml` |
| Started by | A push to `develop` | A tag of the form `vX.Y.Z` |
| Before any credential is used | Nothing | The `verify` job refuses a malformed tag or one that is not on `main`. Then the run waits for my approval |
| How the revision takes traffic | Directly | It is deployed with no traffic under the tag `candidate`, smoke tested on its own address, and only then given the traffic |
| Instance cap | 1 | 1 while it runs as a demonstration, 4 in the design |

Both then run the same steps in the same order.

1. Check that every secret and variable is present. A missing one fails the run
   and names it.
2. Authenticate through Workload Identity Federation as that environment's
   deployer.
3. Build the image and push it. Everything after this uses the digest, never a
   tag.
4. Apply the migrations from the runner, over the direct connection, as
   `toolshed_migrate`. No new revision exists yet, so a failure here leaves the
   running service untouched.
5. Run the seed. It matches on natural keys and only creates what is missing.
6. Deploy the revision and smoke test it.
7. Build the frontend, point its `/api` rewrite at the API from step 6 and
   deploy it.
8. Smoke test again through the frontend domain.
9. Write the commit, the image digest and the Vercel deployment to the run
   summary.

Both services run with minimum instances 0, 1 vCPU, 512 MiB, concurrency 80, a
60 second timeout, CPU allocated only during requests and public invocation
allowed. One deployment runs at a time in each environment, and a running one
is never cancelled to make way for the next, so no migration is cut off part
way through.

The very first deployment of a service takes traffic directly, in production
too, because there is no earlier revision to keep serving.

The repository is public and so are its workflow logs. The Cloud Run address is
masked and filtered out of them. Browsers reach the API only through the
frontend domain.

Production is capped at one instance because an instance cap is the only hard
limit on what a public service can cost. Going live for a paying client means
setting `CLOUD_RUN_MAX_INSTANCES` back to four in `deploy-production.yml`,
which with a pool of five is the twenty connections NFR-15 is worked out from,
and checking the database allowance at the same time.

## Checking a deployment

The smoke test asks for `/api/health` up to twelve times, ten seconds apart,
which allows for a cold start. It accepts only a 200 whose body says
`healthy`. I ask the same question by hand through the frontend domain.

```bash
curl -s https://toolshed-hire-staging.vercel.app/api/health
```

| Field | Meaning |
|---|---|
| `status` | `healthy` with HTTP 200, or `degraded` with HTTP 503 |
| `environment` | Which environment the process believes it is |
| `databaseReachable` | A query completed against the configured database |
| `btreeGistInstalled` | The extension the exclusion constraint depends on is present |
| `revision` | The Cloud Run revision that answered |

The revision name ends with the first seven characters of the commit, the run
number and the attempt, so I can match what is serving to the run that
deployed it. A `degraded` answer with `btreeGistInstalled` false means the
migrations have not been applied to that database.

The first staging deployment, on 2 October 2026, took about four minutes end to
end and answered 200 through the frontend domain with the database reachable.

On staging I also confirmed that the split between the two database roles
holds. Migrations 0001 and 0002 ran as `toolshed_migrate`, including the three
extensions. As `toolshed_app` through the pooler, an update and a delete on
`audit_event` and a delete on `branch` were each refused with SQLSTATE 42501.

Every log line is one JSON object. A line written while a request was served
carries the request id that the API returns in `X-Request-ID` and in every
problem document.

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=ERROR' \
  --limit=20 --project="${PROJECT_ID}"

gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.request_id="REQUEST_ID"' \
  --project="${PROJECT_ID}"
```

## Rollback

| Layer | Action | Rebuild |
|---|---|---|
| API | Shift Cloud Run traffic back to the previous revision | No |
| Frontend | Promote the previous deployment of that Vercel project again | No |
| Database | None. No downgrade is planned | |

The two fast layers are independent. The frontend routes to the service and not
to a revision, so I can roll either one back without touching the other.

```bash
export SERVICE_NAME="toolshed-api-staging"      # or toolshed-api-prod

gcloud run revisions list --service="${SERVICE_NAME}" --region="${REGION}"

gcloud run services update-traffic "${SERVICE_NAME}" \
  --region="${REGION}" --to-revisions=PREVIOUS_REVISION=100
```

The database is left out on purpose. Migrations are written to stay compatible
with the revision that is still serving, so rolling the code back is enough and
the schema simply stays ahead of it. If a migration is itself the defect, I fix
it forward with a new revision of the schema.

A rollback pins the traffic to the revision I named, and a pinned service does
not hand traffic to a new revision by itself. The production workflow shifts
traffic to the latest revision as its own step, so the next release clears the
pin. The staging workflow has no such step. After a rollback on staging, the
next deployment creates a revision that receives nothing, and its smoke test
passes against the old one. So once that deployment has finished I release the
pin myself and confirm that `revision` in the health answer has changed.

```bash
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region="${REGION}" --to-latest
```

Tags are never moved. If a deployment fails and the source has not changed, I
run the same run again. A fix to the source gets a new patch version.

## What it costs

Google's free trial is 300 USD of credit over 90 days. At 90 days the trial
ends whatever is left. The resources are stopped, and they are deleted after a
further 30 days unless the account is upgraded to a paid account. After
upgrading, only usage beyond the Free Tier is billed.

The Free Tier does not expire.

| Line | Free each month | This system |
|---|---|---|
| Cloud Run | 2 million requests, 180,000 vCPU-seconds, 360,000 GiB-seconds | Inside it at demonstration traffic |
| Artifact Registry | 0.5 GB | Held down by the cleanup policy |
| Secret Manager | 6 secret versions, 10,000 access operations | **8 versions, about 0.12 USD a month** |
| Cloud Logging | 50 GiB | Inside it |
| Neon | Free plan, no card | One project, two branches |
| Vercel | Hobby plan | Two projects |

At demonstration traffic the only line above zero is the two extra secret
versions. That figure matches the running costs section of the design document.
A rotated secret gains a version, so I destroy the old one to keep the count at
eight.

The budget from step 2 of `SETUP.md` only warns. It does not cap spending. These
are what keep the bill down, in order of effect.

1. Scale to zero, with CPU allocated only during requests.
2. The instance cap, which is the only hard ceiling on a public service.
3. No scheduled pings. One would keep an instance and the database awake.
4. The image cleanup policy.
5. Small structured logs.

Hobby is for non commercial use, so a paying client means a paid Vercel plan as
well as the higher instance cap.

The cleanup policy always keeps the newest three image versions and deletes the
rest only once they are seven days old. A week with many deployments can
therefore hold more than three, which is why I check the size.

```bash
# Image storage against the 0.5 GB allowance
gcloud artifacts repositories describe "${AR_REPOSITORY}" \
  --location="${REGION}" --format='value(sizeBytes)'
```

## Tearing it all down

```bash
gcloud run services delete toolshed-api-staging --region="${REGION}"
gcloud run services delete toolshed-api-prod --region="${REGION}"
gcloud artifacts repositories delete "${AR_REPOSITORY}" --location="${REGION}"
gcloud projects delete "${PROJECT_ID}"
```

Deleting the Google Cloud project stops all its charges, and it is the only way
to be certain of that. The rest I remove by hand.

- The Neon project, from the Neon console.
- The two Vercel projects and the access token the workflows used.
- The two GitHub environments, which takes their secrets and variables with
  them.
- The budget. It belongs to the billing account and outlives the project.
