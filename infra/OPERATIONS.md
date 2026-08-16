# Running and operating Toolshed Hire

Local development, day to day operations and rollback. `SETUP.md` is what you
follow once. This is what you come back to.

## Local development

PostgreSQL 16 locally, in CI and on Neon. Testing against a different major
version than production is how a constraint that works everywhere except
production gets shipped.

```bash
docker run --name toolshed-postgres \
  -e POSTGRES_USER=toolshed \
  -e POSTGRES_PASSWORD=toolshed \
  -e POSTGRES_DB=toolshed \
  -p 5432:5432 -d postgres:16
```

```bash
cd backend
cp .env.example .env      # then edit it. .env is git ignored and never committed
python -m venv .venv && source .venv/bin/activate   # Scripts/activate on Windows
pip install --editable ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

```bash
cd frontend
npm ci
npm run dev
```

The API answers on <http://localhost:8080> and the Vite dev server on
<http://localhost:5173>. Locally these are two origins, which is why
`CORS_ORIGINS` in `.env.example` lists the dev server. Deployed they are one
origin, because Vercel rewrites `/api/:path*` to Cloud Run, so the CORS
configuration is doing nothing in production and is defence in depth only.

## Running the checks the pipeline runs

Run these before pushing. They are the same commands the workflows use, so a
pass here is a pass there.

```bash
cd backend
ruff check .
mypy app
pytest tests -m "not postgres"     # no database needed
pytest tests -m "postgres"         # needs the container above, migrated

cd ../frontend
npm run lint
npx tsc --build --force
npx vite build
```

## Building the image the way the pipeline builds it

```bash
cd backend
docker build --tag toolshed-hire-api:local .
docker image inspect toolshed-hire-api:local --format='{{.Size}}' \
  | awk '{printf "%.0f MB\n", $1/1024/1024}'
```

The target is roughly 200 MB. If that number starts climbing, the usual cause
is a package that pulled a build dependency into the final stage, and the fix
is in the Dockerfile rather than in the dependency.

Run it against the local database. `host.docker.internal` is how the container
reaches a database running on the host:

```bash
docker run --rm -p 8080:8080 \
  -e ENVIRONMENT=development \
  -e DATABASE_URL="postgresql+psycopg://toolshed:toolshed@host.docker.internal:5432/toolshed" \
  toolshed-hire-api:local

curl -s localhost:8080/api/health | python -m json.tool
```

## Reading the health endpoint

`GET /api/health` is public and reports what it actually verified rather than a
bare acknowledgement.

| Field | Meaning |
|---|---|
| `status` | `healthy` with HTTP 200, or `degraded` with HTTP 503 |
| `environment` | Which environment the process believes it is |
| `database_reachable` | A query completed against the configured database |
| `btree_gist_installed` | The extension the exclusion constraint depends on is present |

A `degraded` response with `btree_gist_installed: false` means migrations have
not been applied to that database. The service will start and serve reads, and
it cannot enforce the constraint that prevents double booking, which is why the
deployment smoke test refuses to accept anything but `healthy`.

## Rollback

The three layers are independent on purpose, and only one of them is fast to
get wrong.

| Layer | Action | Rebuild | Expected time |
|---|---|---|---|
| Frontend | Promote the previous Vercel production deployment | No | Under a minute |
| API | Shift Cloud Run traffic to the previous revision | No | Under a minute |
| Database | Forward fix, or restore a Neon branch to a point in time | Yes for a forward fix | Minutes to hours |

```bash
# What is deployed, newest first
gcloud run revisions list --service="${SERVICE_NAME}" --region="${REGION}"

# Send all traffic back to a known good revision
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region="${REGION}" --to-revisions=REVISION_NAME=100
```

The database is deliberately absent from the routine path. Migrations are
written expand first and contract later, so rolling the code back is sufficient
in the ordinary case and the schema simply stays ahead of it. A downgrade is
reserved for the case where the migration itself is the defect, and even then a
forward fix is preferred.

## What actually costs money

| Line | During build | At go-live |
|---|---|---|
| Google Cloud billing account | **[CARD]** Card required, nothing charged inside the allowance | Same |
| Cloud Run compute | Free allowance | Free allowance |
| Cloud Run egress | Negligible | **Billed from the first byte.** The free egress allowance applies to North America and this service is in Europe. Roughly USD 0.09 a month at the modelled volume |
| Artifact Registry | Free to 0.5 GB | About USD 0.01 a month with the cleanup policy from `SETUP.md` step 3 |
| Secret Manager | Free allowance | Free allowance |
| Neon | Free plan, no card | Free plan |
| Vercel | Hobby, free | **[CARD] Pro, USD 20 per member per month**, because Hobby forbids commercial use |
| GitHub Actions | Free minutes on a private repository | Same, reviewed at each gate |

Every service runs inside a free allowance during build and demonstration. Two
lines leave it at go-live, the Vercel plan and European egress, and both are
quantified above rather than waved away.

### Watching whether the model still holds

These are the commands that tell you.

```bash
# Image storage against the 0.5 GB allowance
gcloud artifacts repositories describe "${AR_REPOSITORY}" \
  --location="${REGION}" --format='value(sizeBytes)'

# Recent errors, without paging through everything else
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=ERROR' \
  --limit=20 --format='value(timestamp, jsonPayload.message)'
```

Neon compute hours are the figure to watch rather than request count. The
health check, not the customers, decides that number, which is why the
availability monitoring is two tiers with the deep check every thirty minutes
rather than one check every five.

## Tearing it all down

```bash
gcloud run services delete "${SERVICE_NAME}" --region="${REGION}"
gcloud artifacts repositories delete "${AR_REPOSITORY}" --location="${REGION}"
gcloud projects delete "${PROJECT_ID}"
```

Delete the Neon project and the Vercel project from their own consoles.
Deleting the Google Cloud project stops all charges, and it is the only way to
be certain of that.
