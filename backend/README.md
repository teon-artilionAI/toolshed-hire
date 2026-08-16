# Toolshed Hire backend

FastAPI and PostgreSQL. This directory is the walking skeleton, which means it
proves the load bearing decisions end to end and nothing else. It is not a
first pass at the whole application.

## What it proves

1. A migration creates the core tables in real PostgreSQL, including the
   `btree_gist` extension.
2. A `daterange` GiST exclusion constraint rejects an overlapping allocation of
   the same physical asset.
3. Two genuinely concurrent transactions cannot double book one unit, because
   candidates are locked with `SELECT ... FOR UPDATE SKIP LOCKED` and the
   constraint has the last word.
4. A React client can call a role protected endpoint and get a correct answer.
5. A constraint violation surfaces as a clean HTTP 409, never a 500.

## Layout

| Path | Layer | Holds |
|---|---|---|
| `app/domain` | Domain | `BookingPeriod`, enumerations, errors. No database access. |
| `app/application` | Application | Use cases and transaction boundaries. |
| `app/infrastructure` | Infrastructure | Engine, SQLModel tables, hashing, tokens. |
| `app/api` | API | Routers, dependencies, problem responses. |
| `alembic` | Migrations | Hand written, because autogenerate cannot invent an exclusion constraint. |

## Running it locally

```bash
python -m venv .venv
.venv/Scripts/activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env            # then edit DATABASE_URL

alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` should report
`{"status": "healthy", "databaseReachable": true, "btreeGistInstalled": true}`.

## Endpoints

| Method | Path | Roles admitted |
|---|---|---|
| GET | `/api/health` | Public by declaration, for the uptime check. |
| POST | `/api/auth/sign-in` | Public, it issues the credential. |
| GET | `/api/me` | Any active account. |
| POST | `/api/allocations` | Any active account. A customer may only book for themselves. |

Every other endpoint added later must declare its roles. The default is deny
(BR-41).

## The constraint

```sql
ALTER TABLE asset_allocations
ADD CONSTRAINT ex_asset_allocations_no_active_overlap
EXCLUDE USING gist (
    asset_id WITH =,
    daterange(start_date, end_date, '[)') WITH &&
) WHERE (released_at IS NULL);
```

Periods are half open. A return on the twelfth frees the twelfth. The same rule
is implemented once in the domain, in `BookingPeriod`, and once in the
database, here. The two must never drift apart.

A violation arrives as SQLSTATE `23P01`. The allocation use case matches on the
code and the constraint name reported in the driver diagnostics, never on the
error message text, and raises `AssetUnavailableConflict`, which the API maps
to a 409 problem document.

## Configuration

Every value comes from the environment. See `.env.example`. Outside
development and test the process refuses to start while `JWT_SECRET` is still
the placeholder or `DATABASE_URL` still points at localhost, because a
deployment that boots on a known secret is a hole nobody notices.

## Tests

The suite is split in two by the `postgres` marker, and the pipeline runs the
two halves as separate jobs.

```bash
pytest tests -m "not postgres"   # unit, component and API tests, no database
pytest tests -m postgres         # the exclusion constraint and concurrency
```

Everything without the marker runs against an in memory SQLite engine and must
never open a network connection. The marked tests need a real PostgreSQL 16
reached through `DATABASE_URL`, because the things they prove, `btree_gist`, a
`daterange` exclusion constraint and two genuinely concurrent transactions, have
no SQLite equivalent. With `DATABASE_URL` unset they skip with a message saying
what to set rather than failing.

The marked tests migrate the database to head themselves and truncate every
table between cases, so point them at a database you are willing to lose. They
refuse to run at all unless `ENVIRONMENT` is `development` or `test`.

### The postgres suite and your seed data cannot share a database

`pytest -m postgres` truncates every table in the schema before and after each
test case. It is not selective, and it does not restore anything afterwards. If
`DATABASE_URL` points at the database you ran `python seed.py` against, the
branches, the catalogue, the assets and the three accounts are gone the moment
the suite runs, and the next sign in from the running application fails with
credentials that were correct five minutes earlier. That has already happened
twice. It is not a bug in the tests. Emptying the tables is what makes a
concurrency test repeatable.

Use two databases. One holds seed data and serves the application, the other is
disposable and belongs to the suite.

```bash
docker run --name tsh-pg -e POSTGRES_USER=toolshed -e POSTGRES_PASSWORD=toolshed \
  -e POSTGRES_DB=toolshed -p 5432:5432 -d postgres:16

# The disposable one, created once.
docker exec tsh-pg psql -U toolshed -d postgres -c "CREATE DATABASE toolshed_test"

# The suite. Note the database name, and note that it is not the seeded one.
ENVIRONMENT=test DATABASE_URL=postgresql+psycopg://toolshed:toolshed@localhost:5432/toolshed_test \
  pytest tests -m postgres
```

If the seed does disappear, `python seed.py` puts it back. The script is
idempotent and matches on natural keys, so running it again costs nothing.
