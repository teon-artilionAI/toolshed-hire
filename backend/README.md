# Toolshed Hire backend

FastAPI and PostgreSQL. This directory is the walking skeleton, which means it
proves the load bearing decisions end to end and nothing else. It is not a
first pass at the whole application.

## What it proves

1. A migration creates the seventeen tables of the documented schema in real
   PostgreSQL, with the `btree_gist`, `citext` and `pg_trgm` extensions, and a
   test reads the catalogue to confirm that what was built is what was
   designed.
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
| `app/domain` | Domain | Entities as plain dataclasses, `BookingPeriod`, enumerations, errors. No framework, no SQL, no IO. |
| `app/application` | Application | Use cases, transaction boundaries and ports. One package per module, plus the unit of work, the clock and the audit log, which every module shares. |
| `app/infrastructure` | Infrastructure | Engine, SQL repositories, the SQL unit of work, the system clock, hashing, tokens. |
| `app/infrastructure/models` | Infrastructure | One SQLModel class per table, one module per subject area. |
| `app/infrastructure/notification` | Infrastructure | The SQL outbox, the Resend adapter and the two gateways that are not Resend. |
| `app/api` | API | Routers, dependencies, middleware, problem responses. `deps.py` is the composition root, and `catalogue_deps.py` is its read side half. |
| `alembic/versions` | Migrations | Hand written, because autogenerate cannot invent an exclusion constraint. |
| `alembic/baseline` | Migrations | The frozen definitions behind migration `0001`, one module per subject area. |
| `alembic/role_grants.py` | Migrations | What the restricted application role may do, behind migration `0002`. |
| `seed_data` | Tooling | The catalogue and the fleet as plain data. It opens no file and no connection. |
| `seeding`, `seed.py` | Tooling | The loader for that data, and its entry point. |
| `scripts` | Tooling | `provision_roles.py`, which creates the two database roles. |

Dependencies point inward only. The domain imports nothing from the other
layers, the application layer imports the domain and nothing else, and the API
layer is the only one that imports everything, because it is where the pieces
are put together.

The design document describes eight modules. Five have code so far, and each
keeps the same name in every layer it appears in.

| Module | Domain | Application | Infrastructure |
|---|---|---|---|
| `identity` | `Actor`, `Branch`, `CustomerProfile` | `BranchRepository`, `CustomerRepository`, `BranchDirectory` | `SqlBranchRepository`, `SqlCustomerRepository`, `SqlBranchDirectory` |
| `catalogue` | `ProductModel`, `Asset` | `ProductModelRepository`, `CatalogueQuery`, `BrowseCatalogue` | `SqlProductModelRepository`, `SqlCatalogueQuery` |
| `availability` | `AssetAllocation` | `AssetRepository`, `allocate_assets`, `AvailabilityQuery`, `SearchAvailability` | `SqlAssetRepository`, `SearchAvailabilityQuery` |
| `booking` | `Reservation`, `ReservationLine` | `ReservationRepository`, `CreateReservationUseCase` | `SqlReservationRepository` |
| `notification` | `Notification`, `EmailMessage` | `NotificationOutbox`, `NotificationGateway`, `NotificationDispatcher` | `SqlNotificationOutbox`, `ResendEmailAdapter`, `FakeEmailGateway` |

`hire`, `money` and `reporting` gain their packages when their first use case
is built. The audit trail belongs to no module, because every module writes to
it, so it has a file of its own in each layer.

## The two patterns in place

The design document names four patterns. Two are built.

### Repository with Unit of Work

One booking writes a reservation, a line, an allocation for every unit, an
audit event and a queued notification. BR-09 and BR-49 need those to commit
together or not at all, so exactly one object owns the transaction.

`UnitOfWork` is a port in the application layer. A use case enters it, works
through the repositories it exposes and calls `commit`. Leaving the block
without a commit rolls everything back. `SqlAlchemyUnitOfWork` implements it
over one `Session`, which it shares with every repository, the audit log and
the outbox.

```python
with self._uow as uow:
    uow.reservations.add(reservation)
    allocated = allocate_assets(uow.assets, self._clock, allocation_command)
    uow.audit.record(event)
    queue_booking_confirmation(uow.notifications, ...)
    uow.commit()
```

Three things live in exactly one place because of it.

- `SqlAssetRepository.lock_allocatable` is the only place that issues
  `SELECT ... FOR UPDATE SKIP LOCKED`.
- `SqlAssetRepository.translate_integrity_error` is the only place a violation
  of the exclusion constraint becomes `AllocationConflictError`.
- `SqlAuditLog.record` writes the audit event in the same transaction as the
  change. If it cannot be written, the change does not happen (BR-49).

Every state changing use case leaves one audit event. It carries the actor and
the role the actor held at the time, the entity and the action, for example
`reservation.held`, the changed fields before and after, the request id and
the client address when the server knows one.

A use case is a class with one `execute(command)` method. It takes the unit of
work, a clock and anything else it needs through its constructor. The router
never builds one. `app/api/deps.py` does, and it is the only module that knows
which implementation stands behind each port a use case writes through. The
query objects of the read side are chosen the same way in
`app/api/catalogue_deps.py`.

### Adapter

`NotificationGateway` is the port. `ResendEmailAdapter` is the only class that
knows which email provider is in use. It calls the Resend HTTP API with a five
second timeout and returns a `DeliveryReceipt`. A status outside the 2xx
range, a timeout and a transport error each come back as a failed receipt with
a short reason. The adapter never raises for a delivery that did not happen.

The `notification` table is a transactional outbox (BR-19).

1. The use case writes the notification `QUEUED` in the same transaction as
   the booking.
2. After the commit, with no transaction open, `NotificationDispatcher` sends
   whatever is queued and records `SENT` with the provider's message id, or
   `FAILED` with the reason.
3. A provider failure never rolls the booking back, and the dispatcher never
   raises.

Dispatch runs inside the request, after the commit and before the response.
Cloud Run only gives a container CPU while it is serving a request, so work
left for a background thread might never run. Every message carries an
`Idempotency-Key` derived from the notification id, so a notification that is
dispatched twice is delivered once.

Only a booking confirmation writes a notification row. The existing flow
creates a held reservation, so that is where the confirmation is queued today.
It moves to the confirmation use case when that is built.

### The clock

Nothing in the domain or the application layer reads the time from the
operating system. A use case is handed a `Clock`. `SystemClock` returns
instants in UTC and works out the business day in `Africa/Johannesburg`, so a
booking made at half past midnight in Cape Town belongs to the new day. The
tests use a clock that stands still, and one test reads the source of both
layers to make sure neither calls `datetime.now()` or `date.today()`.

## The read side

A visitor with no account browses the catalogue and asks where a model is free
for a period (FR-02, FR-03, FR-04). Nothing is written, so there is no unit of
work, no lock and no audit event. A read goes through a query object.

| Port in the application layer | Query object in the infrastructure layer |
|---|---|
| `BranchDirectory` | `SqlBranchDirectory` |
| `CatalogueQuery` | `SqlCatalogueQuery` |
| `AvailabilityQuery` | `SearchAvailabilityQuery` |

A query object selects columns and returns small frozen dataclasses that the
application layer defines, in the `read_models.py` of each module. It never
returns a table row. None of those dataclasses has a field for an asset tag, a
serial number or a number of units, so a customer cannot be told stock (US-07).
The single model question counts free units inside the database and returns
only whether there are enough.

Two services hold the rules that are not SQL. `BrowseCatalogue` refuses an
unknown category and answers an unpublished model as not found.
`SearchAvailability` builds the period as a `BookingPeriod` and checks it with
`ensure_within_booking_window`, so a search and a booking agree about BR-02 to
BR-05. The day it is comes from the clock.

A unit is free for a period when its status is `AVAILABLE` and it holds no
active allocation whose half open period overlaps the one asked about (BR-10).
The availability list answers for every model on the page and every active
branch in one statement. The condition is written with the same
`daterange(start_date, end_date, '[)') &&` expression as the exclusion
constraint, under `released_at IS NULL`, so the GiST index behind the
constraint can serve it, and the partial index `ix_asset_available` finds the
hireable units. An availability search issues the count and the page, plus one
lookup for a category and one for a branch when the search names them, whatever
the page holds. `app/infrastructure/availability_search.py` says how the
planner runs the statement and what slows down first as the fleet grows.

The order of a list comes from the `ModelSort` enumeration, which the query
object maps to columns. No part of a request is ever placed in a statement
(C-28).

Every query logs when it starts and when it finishes, with its filters, its row
count and its duration. The text a visitor searched for is logged by its length
only.

## The schema

Migration `0001` is the baseline. It creates seventeen tables with singular
snake_case names, which are the sixteen domain tables and `rate_limit_counter`.

| Subject area | Tables |
|---|---|
| Identity and access | `branch`, `user_account`, `customer_profile`, `refresh_session` |
| Catalogue and fleet | `category`, `product_model`, `asset` |
| Booking and allocation | `reservation`, `reservation_line`, `asset_allocation` |
| Hire and money | `rental`, `rental_item`, `damage_report`, `charge` |
| Evidence and supporting | `audit_event`, `notification`, `rate_limit_counter` |

The same five subject areas name the modules in `app/infrastructure/models`
and in `alembic/baseline`. The two are kept apart on purpose. The models change
as the application grows. The baseline is a snapshot that imports nothing from
`app`, so an edit to a model can never change what an already released
migration creates. A later change to the schema is a new revision.

The migration is the one authoritative listing of the check constraints, the
exclusion constraint and the indexes. The models declare columns and keys and
do not repeat them.

## The seed and the two database roles

`python seed.py` gives a database a fleet worth looking at, so the system has
real data from its first deployment. In one transaction it loads the three
branches, fourteen categories, 120 published product models, 400 physical
units (171 at CBD, 125 at BLV, 104 at SMW), five accounts with verified email
addresses and a profile for each of the two customers, and the worked example
from the design document as a hire that is already closed.

Thirty four units keep the tags the prototype showed. The other 366 are tagged
`TSH-<prefix>-<number>`, numbered upward within each prefix in SKU order and
then branch order, stepping over any number a pinned unit carries, so the same
data always gives the same tags. Stock bought after the first load belongs in
`seed_data/pinned_assets.py` with the tag it was given, because a new product
model can renumber the generated units that sort after it.

Every row is matched on its natural key, and a row that is already there is
left exactly as it is. A second run changes nothing and logs
`seed.nothing_to_do`, and a run against a database in use never resets a
status, a price or a password. Every account the seed creates gets the
password in `SEED_PASSWORD`. Outside development and test the script refuses to
run without it. If `SEED_CUSTOMER_PASSWORD` is set as well, the customer
accounts get that password instead, so a demonstration customer login can be
published without exposing the staff and admin logins. The data lives in
`seed_data` and the loading in `seeding`.

The design document splits database authority between two roles, so the
running application can neither change the schema nor rewrite its audit trail.

| Role | Used by | May do |
|---|---|---|
| `toolshed_migrate` | `alembic upgrade head` | Create objects in this database and in the `public` schema. |
| `toolshed_app` | The running API | Select, insert and update on every table. On `audit_event`, select and insert only. Delete on `rate_limit_counter` alone, where expired windows are removed. |

The owner of the database creates the roles once, before the first migration.
Revision `0002` then gives `toolshed_app` its privileges on the tables.

```bash
DATABASE_OWNER_URL=postgresql://owner:...@host:5432/toolshed APP_ROLE_PASSWORD=... MIGRATE_ROLE_PASSWORD=...   python scripts/provision_roles.py

DATABASE_URL=postgresql+psycopg://toolshed_migrate:...@host:5432/toolshed alembic upgrade head
DATABASE_URL=postgresql+psycopg://toolshed_migrate:...@host:5432/toolshed python seed.py
```

The API is then started with a `DATABASE_URL` that names `toolshed_app`. The
script is safe to run again, which is also how a password is rotated, and it
never logs a password.

A plain local database with one owner needs none of this. If `toolshed_app`
does not exist when revision `0002` runs, the revision logs that it skipped the
grants and the migration still succeeds. To restrict a database migrated that
way, I provision the roles and run `alembic downgrade 0001` and then
`alembic upgrade head`. The downgrade only revokes, so no data is touched.

Any later migration that creates a table or a sequence has to grant on it in
the same revision. A new object inherits no privileges, so a table added
without its grant is one the application cannot read.

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
`{"status": "healthy", "databaseReachable": true, "btreeGistInstalled": true, "revision": "local"}`.

## Endpoints

| Method | Path | Roles admitted |
|---|---|---|
| GET | `/api/health` | Public by declaration, for the uptime check. |
| POST | `/api/auth/sign-in` | Public, it issues the credential. |
| GET | `/api/me` | Any active account. |
| POST | `/api/allocations` | Any active account. A customer may only book for themselves. |
| GET | `/api/branches` | Public by declaration. |
| GET | `/api/catalogue/categories` | Public by declaration. |
| GET | `/api/catalogue/models` | Public by declaration. |
| GET | `/api/catalogue/models/{slug}` | Public by declaration. |
| GET | `/api/catalogue/availability` | Public by declaration. |
| GET | `/api/catalogue/models/{slug}/availability` | Public by declaration. |

Every other endpoint added later must declare its roles. The default is deny
(BR-41). The six public read routes say so in code. Each depends on
`public_access` from `app/api/deps.py`, and a test fails if one of them stops.

### The public catalogue and availability routes

All six return JSON with camelCase member names. Money is a string with two
decimals, for example `"280.00"`, and never a number. A date is `YYYY-MM-DD`
and a time of day is `HH:MM`.

| Path | Query | Returns |
|---|---|---|
| `/api/branches` | none | `items`, the active branches ordered by name. |
| `/api/catalogue/categories` | none | `items`, the active categories, each parent followed by its children. `modelCount` counts published models and a parent includes its children. |
| `/api/catalogue/models` | `category`, `q`, `sort`, `page`, `pageSize` | `items`, `page`, `pageSize`, `total`, for published models only. |
| `/api/catalogue/models/{slug}` | none | One published model, with `longDescription` and `lateFeePerDay`. 404 for an unknown or unpublished slug. |
| `/api/catalogue/availability` | `from`, `to`, the five above, `branch` | `from`, `to`, `hireDays`, `items`, `page`, `pageSize`, `total`. Each item is a `model` and one `available` boolean for every active branch. |
| `/api/catalogue/models/{slug}/availability` | `from`, `to`, `quantity` | `from`, `to`, `hireDays`, `quantity`, `branches`. A branch is available when at least `quantity` units are free. |

`category` is a category slug and a parent includes its children. `q` is at
least 2 characters and is matched against the name, the manufacturer and the
model number in any case. `sort` is `name`, `dailyRateAsc` or `dailyRateDesc`.
`page` counts from 1 and `pageSize` is 1 to 50, 24 when left out. `branch` is a
branch code and keeps only the models free at that branch. `quantity` is 1 to
10. `from` and `to` are half open, so `to` is the day the equipment comes back
and is free again.

A refused parameter is a 422 problem document. The type ends in
`request-validation-failure` and `errors.fields` holds one sentence for each
refused field, keyed by where the value came from and its name in the query,
for example `query.to` or `query.pageSize`. The shape is the same whether the
value could not be read or a rule refused it. The rules are that `to` is after
`from`, the period is at most 28 days and within the hire limits of the model
on the single model route, `from` is not in the past and not more than 90 days
ahead, and the category, the branch and the sort order are known.

The four catalogue routes answer `Cache-Control: public, max-age=60`. The two
availability routes answer `no-store`, because the answer can be wrong a second
after it is given. A request that carried a credential is always answered
`no-store`.

`openapi.json` in this directory is the OpenAPI document of the API, kept so
the frontend can generate its types from it. I write it from Python and not by
redirecting standard output, because the application logs to standard output.

```bash
ENVIRONMENT=test python -c "import json, pathlib; from app.main import create_app; pathlib.Path('openapi.json').write_text(json.dumps(create_app().openapi(), indent=2) + '\\n', encoding='utf-8')"
```

`/docs`, `/redoc` and `/openapi.json` are served in development and test only.
In staging and production they answer 404.

## Request ids, logs and headers

Every request has an id. A valid UUID sent in `X-Request-ID` is kept, and
anything else is replaced by a new UUID4. The same value comes back in the
`X-Request-ID` response header, as `requestId` in every problem document and
as `request_id` on every log line written while the request was served. To
trace a failure I ask for the `requestId` and search the log for it.

Each request writes one access log line, `http.request_completed`, when its
response is finished.

| Field | Holds |
|---|---|
| `method` | The HTTP method. |
| `route` | The route template, for example `/api/reservations/{reservation_id}`, and `unmatched` when no route matched. Never the requested path. |
| `status` | The status code that was sent. |
| `duration_ms` | How long the request took, in milliseconds. |
| `actor_role` | The stored role of the authenticated caller, or `anonymous`. |
| `outcome` | `success`, `client_error` or `server_error`. |
| `request_id` | The id above. |

The line is written at `INFO`, at `WARNING` for a 4xx and at `ERROR` for a 5xx.

Secrets are removed from every log line before it is written (C-42). The value
of any `extra` key whose name contains `password`, `secret`, `token`,
`authorization`, `cookie`, `api_key` or `database_url` becomes `[REDACTED]`,
and the password in any `scheme://user:password@host` address is replaced the
same way. A harmless key that happens to contain one of those words is redacted
too, so I name such keys differently.

Every response carries the security headers of C-06 to C-12, which are listed
in `app/api/security_headers.py`. `Strict-Transport-Security` is sent in
staging and production only, and `Cache-Control: no-store` whenever the request
carried an `Authorization` header or a cookie.

`GET /api/health` also reports `revision`. Cloud Run sets `K_REVISION` on every
instance, so the field names the revision that answered. Anywhere else it is
`local`.

## The constraint

```sql
ALTER TABLE asset_allocation
ADD CONSTRAINT asset_allocation_no_overlap
EXCLUDE USING gist (
    asset_id WITH =,
    daterange(start_date, end_date, '[)') WITH &&
) WHERE (released_at IS NULL);
```

Periods are half open. A return on the twelfth frees the twelfth. The same rule
is implemented once in the domain, in `BookingPeriod`, and once in the
database, here. The two must never drift apart.

An allocation is active exactly while `released_at` is null. Releasing one
stamps `released_at` and `release_reason` together, which a check constraint
enforces, and the row drops out of the constraint without being deleted.

A violation arrives as SQLSTATE `23P01`. `SqlAssetRepository` matches on the
code and on the constraint name, both read from the driver diagnostics and
never from the error message text, and raises `AllocationConflictError`, which
the API maps to a 409 problem document. An integrity error that is not this
constraint is re-raised unchanged.

## Configuration

Every value comes from the environment. See `.env.example`. Outside
development and test the process refuses to start while `JWT_SECRET` is still
the placeholder or `DATABASE_URL` still points at localhost, because a
deployment that boots on a known secret is a hole nobody notices.

`ENVIRONMENT` is `development`, `test`, `staging` or `production`. Staging is
held to every check production is.

Three settings control email.

| Variable | Default | Meaning |
|---|---|---|
| `RESEND_API_KEY` | unset | The Resend API key. Unset, blank or the literal `not-configured-yet` means email is off. |
| `EMAIL_FROM` | `Toolshed Hire <onboarding@resend.dev>` | The From header of every email. |
| `EMAIL_ALLOWED_RECIPIENT` | unset | When set, the only address the service will send to. |

With email off the application still starts. It logs one warning,
`notification.email_not_configured`, and every confirmation is recorded as
`FAILED` with the reason that email is not configured in this environment.

`EMAIL_ALLOWED_RECIPIENT` is how the demonstration environment runs without a
verified sending domain. It is enforced inside the adapter, on the server. A
message for any other address is refused before the provider is called, and it
is never redirected to the allowed address, because that would deliver one
customer's booking to somebody else.

The key is never logged and never appears in a receipt or an error message.

## Checks

I run these from this directory before I publish a change. The pipeline runs
the same commands.

```bash
ruff check .                     # lint, including S608 and C901 at complexity 10
mypy app                         # strict type check
lint-imports                     # the layer contract
pytest tests -m "not postgres"   # unit, component and API tests, no database
pip-audit                        # known vulnerabilities in the installed packages
```

`lint-imports` reads five contracts from `pyproject.toml`.

1. `app.domain` imports nothing from the other three layers.
2. `app.application` does not import `app.api`.
3. `app.application` does not import `app.infrastructure`. The use cases depend
   on ports, and `app.api` is the composition root that wires the
   implementations in.
4. `app.infrastructure` does not import `app.api`.
5. Neither `app.domain` nor `app.application` imports SQLAlchemy, SQLModel,
   FastAPI, Starlette, pydantic, httpx or psycopg.

The full run needs a real PostgreSQL 16. I start the one described by
`docker-compose.yml` at the repository root, which holds a single disposable
database called `toolshed_test`, and I stop it afterwards.

```bash
docker compose up -d --wait

ENVIRONMENT=test DATABASE_URL=postgresql+psycopg://toolshed:toolshed_local_only@localhost:5432/toolshed_test \
  pytest tests --cov --cov-report=term-missing --cov-report=xml

docker compose stop
```

That run is the only one gated on coverage. It measures `app/domain` and
`app/application` and fails below 70 percent. The run without PostgreSQL
carries no `--cov` flag, so it is never held to the threshold. The password in
the compose file is a local throwaway and the port is bound to 127.0.0.1. I set
`TOOLSHED_DB_PORT` when 5432 is already taken.

## Tests

The suite is split in two by the `postgres` marker, and the pipeline runs the
two halves as separate jobs.

```bash
pytest tests -m "not postgres"   # unit, component and API tests, no database
pytest tests -m postgres         # the schema, the constraint, concurrency, the seed and the roles
```

The tests without the marker come in three kinds. `tests/unit` uses no database
at all, and it runs the use cases against an in memory unit of work and a fake
email gateway, which is what depending on ports makes possible. `tests/component`
runs the real repositories and the real unit of work on in memory SQLite.
`tests/api` goes through HTTP on the same SQLite engine. None of them may open
a network connection, and every test client is given the fake email gateway. The marked tests need a real PostgreSQL 16
reached through `DATABASE_URL`, because the things they prove, `btree_gist`, a
`daterange` exclusion constraint and two genuinely concurrent transactions, have
no SQLite equivalent. With `DATABASE_URL` unset they skip with a message saying
what to set rather than failing.

The marked tests migrate the database to head themselves and truncate every
table between cases, so point them at a database you are willing to lose. They
refuse to run at all unless `ENVIRONMENT` is `development` or `test`.

The role tests need no setup. They create `toolshed_app` and `toolshed_migrate`
through `scripts/provision_roles.py`, using the connection in `DATABASE_URL` as
the owner, and apply the grants through the function revision `0002` calls. The
passwords they set are throwaway values in `tests/support/roles.py`. Roles
belong to the cluster and not to one database, so the two roles stay behind
after the run.

`tests/integration/test_schema_baseline.py` runs before every other test. It
reads the PostgreSQL catalogue and asserts that the three extensions, the
seventeen tables, the seventeen enumerated types, the exclusion constraint with
its exact definition and the partial indexes all exist. Every other integration
test assumes that schema, so a broken migration is reported once at the top
instead of as a page of unrelated failures. The order is set by the collection
hook in `tests/integration/conftest.py`, which needs no plugin.

### The postgres suite and your seed data cannot share a database

`pytest -m postgres` truncates every table in the schema before and after each
test case. It is not selective, and it does not restore anything afterwards. If
`DATABASE_URL` points at the database you ran `python seed.py` against, the
branches, the catalogue, the assets and the seeded accounts are gone the moment
the suite runs, and the next sign in from the running application fails with
credentials that were correct five minutes earlier. That has already happened
twice. It is not a bug in the tests. Emptying the tables is what makes a
concurrency test repeatable.

Use two databases. One holds seed data and serves the application, the other is
disposable and belongs to the suite.

```bash
# The seeded one, which serves the running application.
docker run --name tsh-pg -e POSTGRES_USER=toolshed -e POSTGRES_PASSWORD=toolshed \
  -e POSTGRES_DB=toolshed -p 5432:5432 -d postgres:16

# The disposable one, from docker-compose.yml at the repository root. I move it
# to 5433 here because the seeded database already holds 5432.
TOOLSHED_DB_PORT=5433 docker compose up -d --wait

# The suite. Note the port and the database name, and note that it is not the
# seeded one.
ENVIRONMENT=test DATABASE_URL=postgresql+psycopg://toolshed:toolshed_local_only@localhost:5433/toolshed_test \
  pytest tests -m postgres
```

If the seed does disappear, `python seed.py` puts it back. The script is
idempotent and matches on natural keys, so running it again costs nothing.
