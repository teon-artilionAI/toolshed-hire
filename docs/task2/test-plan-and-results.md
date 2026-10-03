# Test plan and results

How I test Toolshed Hire, when each kind of test runs, and what the latest runs
showed. The last section maps each non-functional requirement of the Task 1
design document to how I verify it today.

## The strategy

Each layer of tests proves what the layer below it cannot. The business rules
are tested on their own first, with no database and no clock, because that is
where a mistake costs the most and where a test is cheapest. Anything that only
PostgreSQL can prove, such as the exclusion constraint, row locks and two
transactions at once, is tested against a real PostgreSQL 16, the version that
runs in production. The browser tests then drive the built site against the
real API.

| Layer | Where | What it proves | What it needs |
|---|---|---|---|
| Domain unit tests | [backend/tests/unit](../../backend/tests/unit) | The rules on their own. The pricing and late fee policies, money and VAT, the eight reservation states, the asset states, the settlement, the lockout window, the no show rules | Nothing. No database, no network, a clock that stands still |
| Application tests | [backend/tests/unit](../../backend/tests/unit) | Every use case end to end against an in memory unit of work and a fake email gateway, including the audit event each one writes | Nothing, which is what depending on ports makes possible |
| Component tests | [backend/tests/component](../../backend/tests/component) | The real repositories and the real unit of work | SQLite in memory |
| API tests | [backend/tests/api](../../backend/tests/api) | Every route, every answer and every refusal it can give, the access policy of every route, the role matrix, plain refusal messages, security headers, request ids and the access log | SQLite in memory and the fake email gateway |
| Integration tests | [backend/tests/integration](../../backend/tests/integration) | The schema as designed, the exclusion constraint, concurrency, the grants of the restricted role, the seed, and that each hot query uses its index | PostgreSQL 16, migrated from empty |
| Frontend unit and component tests | `frontend/src/**/*.test.ts(x)`, for example [SC14-Checkout-Deposit.test.tsx](../../frontend/src/features/counter/SC14-Checkout-Deposit.test.tsx) | Every screen on the API with its loading, failed and empty states, the session, the guards, and that no token reaches browser storage | jsdom, with `fetch` answered from a table of routes |
| Browser and accessibility tests | [frontend/e2e](../../frontend/e2e) | The customer and counter journeys in a real browser, an axe scan against WCAG 2.2 AA, and every counter screen at 360 pixels wide | The production build, the real API and a seeded PostgreSQL |
| Deployed smoke test | [smoke-test.sh](../../infra/scripts/smoke-test.sh) | The new revision answers healthy with its database reachable, first on its own address and then through the site | The deployed environment |

The browser tests run every journey twice, once in desktop Chromium and once
in a phone viewport 390 pixels wide. With `E2E_REQUIRE_BACKEND=1`, which the
pipeline sets, a journey that cannot reach the API fails instead of skipping
itself.

## When each test runs

| When | What runs | Workflow |
|---|---|---|
| Every push to any branch | Secret scan. Ruff, strict mypy over the application and the tools, the five layer contracts, and every backend test that needs no database. The frontend lint, the TypeScript check, the unit and component tests, and a check that the generated API types match the OpenAPI document | [ci-fast.yml](../../.github/workflows/ci-fast.yml) |
| Every pull request into `develop` or `main` | The branch policy. Migrations from an empty PostgreSQL 16. The whole backend suite against that database with the coverage gate. `pip-audit` and the npm audit. The production build. The browser and accessibility tests against the real API and a freshly seeded database | [ci-integration.yml](../../.github/workflows/ci-integration.yml) |
| Every merge into `develop` | The migrations and the seed against the staging database, then the smoke test of the new revision and again through the staging site | [deploy-staging.yml](../../.github/workflows/deploy-staging.yml) |
| Every release tag | A check that the tag is well formed and on `main`, my approval, then the migrations, the candidate revision with no traffic, the smoke test of the candidate, the traffic shift and the smoke test through the production site | [deploy-production.yml](../../.github/workflows/deploy-production.yml) |

A pull request cannot merge until the outcome jobs of both check workflows have
passed on an up to date branch.

The API tests also keep two documents honest. A test fails when the committed
[openapi.json](../../backend/openapi.json) differs from what the application
generates, and the frontend check fails when its generated types differ from
that document. So the wire types of the two halves cannot drift apart without
the build saying so.

## The coverage gate

The gated run measures `app/domain` and `app/application`, the two layers that
hold the rules, and fails below 70 percent. The floor is set in
[pyproject.toml](../../backend/pyproject.toml). It only applies to the run with
PostgreSQL, so the fast run is judged on its tests alone and never on a figure
measured over part of the suite. The measured figure has been 100 percent of
lines since the reservation lifecycle merged.

Two tests guard a rule that coverage cannot.
[test_one_place_for_a_price.py](../../backend/tests/unit/test_one_place_for_a_price.py)
and
[test_one_place_for_a_late_fee.py](../../backend/tests/unit/test_one_place_for_a_late_fee.py)
read every module of the application and fail if any code other than the policy
multiplies a rate or a late fee by a number of days.

## How concurrency is tested

Double booking is the first problem this system exists to solve, so the races
are tested the way they would really happen, through HTTP, against PostgreSQL,
with every request on a connection of its own and a barrier releasing them
together.

| Test | The race | What must hold |
|---|---|---|
| [test_concurrent_holds.py](../../backend/tests/integration/test_concurrent_holds.py) | Twenty customers hold the same model for the same dates at the same moment, and five identical units are on the shelf | Exactly five holds answered 200, fifteen answered 409 with a plain message, no 500, no unit held twice and no reservation half held. It passed 24 runs in a row when it was written |
| [test_concurrent_allocation.py](../../backend/tests/integration/test_concurrent_allocation.py) | The same race on the allocation alone, with the row lock bypassed | The exclusion constraint refuses the second booking on its own |
| [test_checkout_race.py](../../backend/tests/integration/test_checkout_race.py) | Two checkouts of one reservation at the same moment | One rental, answered 201 and then 200 with the same rental, no unit put on hire twice and no charge raised twice. The race runs more than once |
| [test_hold_expiry_sweep.py](../../backend/tests/integration/test_hold_expiry_sweep.py) | Two sweeps of expired holds at once, one held at its commit until PostgreSQL reports the other waiting behind it | The second sweep finds nothing left to do |
| [test_no_show_races.py](../../backend/tests/integration/test_no_show_races.py) | Two no show sweeps at once, and two no shows of one customer at once | Each booking is marked once and each strike is counted once, because the second waits for the first and then counts it |
| [test_return_races_and_overdue.py](../../backend/tests/integration/test_return_races_and_overdue.py) | Two returns of one unit at once | One return, and the second answered 409 |

Two things make the holds safe, and the tests prove both. The candidate units
are locked with `SELECT ... FOR UPDATE SKIP LOCKED`, so concurrent bookings take
different units. The `daterange` exclusion constraint on active allocations has
the last word, and a violation becomes a clean 409 and never a 500.

The same tests also prove that a failure leaves nothing behind.
[test_checkout_transaction.py](../../backend/tests/integration/test_checkout_transaction.py)
and
[test_return_transaction.py](../../backend/tests/integration/test_return_transaction.py)
make a checkout and a return fail at the audit write and at the commit, and find
that nothing was kept.

## Results

<!-- final: refresh every figure in this section from the last pull request before task2-v1.0 -->

These are the figures from the pull request that merged returns and settlement,
[#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50), on 3 October
2026.

| Check | Result |
|---|---|
| Backend tests | 3,272 passed on PostgreSQL 16 |
| Coverage of the domain and application layers | 100 percent of lines, against a floor of 70 |
| Ruff | Clean |
| mypy, strict | Clean on 218 files |
| Layer import contracts | 5 kept |
| Frontend unit and component tests | 1,016 passed |
| Frontend lint and type check | Clean |
| Generated API types | Match the OpenAPI document |
| Production build | Clean |
| Browser and accessibility tests | 106 passed against the real API and a freshly seeded PostgreSQL, none skipped |

How the suite grew with each change is recorded in the "Manual verification"
section of every pull request, from 73 backend tests in the first one to the
figures above.

The worked example from the Task 1 design document holds through the API and on
staging. A hire with a R1,200.00 deposit at a late fee of R120.00 a day, returned
two days late, has R240.00 withheld, R960.00 released and R0.00 due, and the
rental is settled. [test_returns.py](../../backend/tests/api/test_returns.py)
follows it through the routes, and
[test_rental_reads_like_the_worked_example.py](../../backend/tests/integration/test_rental_reads_like_the_worked_example.py)
compares a rental opened at the counter with the seeded one.

## Non-functional requirements

Each target is the one in the Task 1 design document, summed up in my own words.
The status says honestly how far I have verified it today.

| NFR | What it asks for | How I verify it today | Status |
|---|---|---|---|
| NFR-01 | A fast availability search on the deployment, with a set budget for server time | The search answers a whole page of models for every branch in a fixed number of statements, which [test_availability_list.py](../../backend/tests/integration/test_availability_list.py) counts. Its query plan ran in under a millisecond on the seeded fleet and in about two milliseconds at ten times the data when it was built. There is no load test against the deployed revision yet | Not yet verified on the deployment <!-- final: load test result --> |
| NFR-02 | The first request after an idle spell finishes within a set time, slow requests show progress, and no button is pressed twice | Every screen on the API shows a loading state, and every write button is disabled while its request is in flight, which the component tests check. The smoke test allows for a cold start. The cold start measured on production is <!-- final: measured cold start --> | Partly met |
| NFR-03 | Twenty concurrent holds for five units give five holds and fifteen clean refusals, and the write path is fast | [test_concurrent_holds.py](../../backend/tests/integration/test_concurrent_holds.py) on every pull request. The response time of the writes has not been measured on the deployment | Met for correctness. Speed not yet measured |
| NFR-04 | A year's report and its export finish within a set time | Reporting is not built yet | Planned for the final release <!-- final: 017 --> |
| NFR-05 | 99 percent availability over trading hours, measured by scheduled checks | No scheduled checks run. Only the deployment smoke tests check the health of the service. [deviations.md](deviations.md) says why | Not in place |
| NFR-06 | A dropped connection never leaves an operation half done, and a signed in assistant resumes without signing in again | [test_checkout_transaction.py](../../backend/tests/integration/test_checkout_transaction.py) and [test_return_transaction.py](../../backend/tests/integration/test_return_transaction.py) fail an operation part way and find nothing kept. [session.spec.ts](../../frontend/e2e/session.spec.ts) shows a reload keeps the session. Cutting the database connection in the middle of a transaction, and the manual drill, are not done | Partly met |
| NFR-07 | HTTPS with HSTS, a strict Content Security Policy, a strict refresh cookie and tokens kept out of browser storage | The headers are in [vercel.json](../../frontend/vercel.json) and [security_headers.py](../../backend/app/api/security_headers.py), checked by [test_security_headers.py](../../backend/tests/api/test_security_headers.py). The browser tests run every screen under the same policy. [web-storage.test.ts](../../frontend/src/shared/web-storage.test.ts) proves no token reaches storage. A header and TLS scan of the deployed site is planned in issue [#22](https://github.com/teon-artilionAI/toolshed-hire/issues/22) | Partly met |
| NFR-08 | Passwords of twelve characters or more, bcrypt at work factor 12, a lockout, and the same answer and timing for a wrong password and an unknown address | [test_login_lockout_window.py](../../backend/tests/api/test_login_lockout_window.py) and [test_login_throttle_and_timing.py](../../backend/tests/api/test_login_throttle_and_timing.py). The timing test counts one bcrypt check on every path and compares medians over five samples, not the hundred the design asks for. The hashing time on the Cloud Run instance has not been measured | Partly met |
| NFR-09 | No route without a declared policy, another customer's record answered 404, another branch's write answered 403 | The application refuses to start on a route with no policy. [test_route_policies.py](../../backend/tests/api/test_route_policies.py) enumerates the routes and holds the role matrix, and [test_ownership_and_branch_scope.py](../../backend/tests/api/test_ownership_and_branch_scope.py) covers ownership and branch scope | Met |
| NFR-10 | Every change writes its audit event in the same transaction, and the application cannot update or delete one | [test_application_role.py](../../backend/tests/integration/test_application_role.py) has an update, a delete and a truncate refused for the application role. The transaction tests show a failed audit write fails the operation | Met for every operation built so far |
| NFR-11 | A walk-in booking and checkout within a set time after short training, proved in moderated sessions | The counter screens have one main action each, and every confirmation says in words what will happen and to which unit. No moderated sessions have been run | Planned before handover |
| NFR-12 | One problem format, no internal detail in an error, a conflict that names the model and dates, and an empty state on every list | Every error is a problem document. [test_plain_refusals.py](../../backend/tests/api/test_plain_refusals.py) fails on a rule identifier or a raw value in a message, [test_allocation_conflict_translation.py](../../backend/tests/integration/test_allocation_conflict_translation.py) proves a constraint violation is a 409, and every list on the API has an empty state | Met for the screens on the API. The screen by screen review is planned in [#22](https://github.com/teon-artilionAI/toolshed-hire/issues/22) |
| NFR-13 | WCAG 2.2 AA on all 24 screens, 44 pixel targets, keyboard use, and layouts from 360 pixels wide | axe scans every screen on the API on every pull request and fails on a serious or critical finding. [narrow-screens.spec.ts](../../frontend/e2e/narrow-screens.spec.ts) checks the counter and account screens at 360 pixels. The keyboard and screen reader passes are not recorded yet, and the seven screens still on sample data are not scanned loaded | Partly met <!-- final: after 022 --> |
| NFR-14 | Layer boundaries, no type errors, low complexity, short files and a coverage floor, all blocking a merge | The five contracts, strict mypy, the TypeScript check, Ruff with a complexity limit of 10 and the coverage floor block every merge. Seven source files are a few lines over the 300 line guide, which no check enforces, and no lint rule bans `any` in the frontend, although none is used | Mostly met |
| NFR-15 | The searches and reports hold at ten times the fleet, on indexed paths, within the connection ceiling | Planner tests prove each counter read and the customer search use their index, in [test_counter_read_indexes.py](../../backend/tests/integration/test_counter_read_indexes.py) and [test_customer_search_index.py](../../backend/tests/integration/test_customer_search_index.py). The availability query was checked at ten times the data. No volume test at the stated row counts has been run, and the instance cap is one, not four | Partly met |
| NFR-16 | Only the last four characters of an identity document, no card data, a privacy notice, and a customer can export and correct their own data | The schema has no column for a full document number or a card. The privacy notice is at `/privacy`. A customer corrects their own details on SC-09. Export, the retention period, anonymisation and the breach procedure are not built | Partly met |
| NFR-17 | Where personal information is held is recorded and disclosed, and no customer data leaves in logs or pipeline artifacts | The privacy notice names Neon and Google Cloud in London, Vercel and Resend. Search text is logged by its length only, and secrets are redacted from every log line. The register of processing and an automated check of pipeline artifacts are not done | Partly met |
| NFR-18 | Structured logs, a health check, migrations that apply forward, a fast rollback and a tested restore | Every log line is JSON with the request id, route, role and outcome, checked by [test_access_log.py](../../backend/tests/api/test_access_log.py) and [test_log_redaction.py](../../backend/tests/unit/test_log_redaction.py). The health check reports the database and the revision. Migrations run from empty on every pull request and over the seeded staging database on every merge. Rollback is written up in [OPERATIONS.md](../../infra/OPERATIONS.md). The rollback rehearsal and the restore drill are not done | Partly met <!-- final: rollback rehearsal --> |

The checks the design keeps for a release, which are the load test, the cold
start measurement, the header and TLS scan and the volume test, and the checks
it keeps for handover, which are the usability sessions, the interruption
drill, the privacy review and the restore drill, are the main work still open
on this table.
