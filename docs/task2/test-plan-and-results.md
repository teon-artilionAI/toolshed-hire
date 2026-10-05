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
real API, and after every deployment the deployed site itself is checked.

| Layer | Where | What it proves | What it needs |
|---|---|---|---|
| Domain unit tests | [backend/tests/unit](../../backend/tests/unit) | The rules on their own. The pricing and late fee policies, money and VAT, the eight reservation states, the asset states, the settlement and its rework after a correction, the report's day counting and the share of a hire charge, the lockout window, the no show rules | Nothing. No database, no network, a clock that stands still |
| Application tests | [backend/tests/unit](../../backend/tests/unit) | Every use case end to end against an in memory unit of work and a fake email gateway, including the audit event each one writes | Nothing, which is what depending on ports makes possible |
| Component tests | [backend/tests/component](../../backend/tests/component) | The real repositories and the real unit of work | SQLite in memory |
| API tests | [backend/tests/api](../../backend/tests/api) | Every route, every answer and every refusal it can give, the access policy of every route, the role matrix, plain refusal messages, security headers, request ids and the access log | SQLite in memory and the fake email gateway |
| Integration tests | [backend/tests/integration](../../backend/tests/integration) | The schema as designed, the exclusion constraint, concurrency, the grants of the restricted role, the seed, and that each hot query uses its index | PostgreSQL 16, migrated from empty |
| Frontend unit and component tests | `frontend/src/**/*.test.ts(x)`, for example [SC14-Checkout-Deposit.test.tsx](../../frontend/src/features/counter/SC14-Checkout-Deposit.test.tsx) | Every screen on the API with its loading, failed and empty states, the session, the guards, and that no token reaches browser storage | jsdom, with `fetch` answered from a table of routes |
| Browser and accessibility tests | [frontend/e2e](../../frontend/e2e) | The customer, counter and owner journeys in a real browser, 109 axe scans across all 24 screens and their states against WCAG 2.2 AA, and a layout sweep of every screen at 360, 768 and 1440 pixels wide | The production build, the real API and a seeded PostgreSQL |
| Deployed smoke test | [smoke-test.sh](../../infra/scripts/smoke-test.sh) | The new revision answers healthy with its database reachable, first on its own address and then through the site | The deployed environment |
| Deployed header and TLS check | [check-security-headers.sh](../../infra/scripts/check-security-headers.sh) | The page and an API answer through the rewrite carry HSTS of at least half a year (15,768,000 seconds, what NFR-07 asks for), a Content Security Policy that denies by default and refuses framing, `nosniff` and the referrer and permissions policies, plain HTTP is redirected, and TLS 1.1 is refused while a TLS 1.2 control connects, both probed with `openssl s_client` | The deployed site |
| Journeys on staging | The three journeys in [release-journeys.spec.ts](../../frontend/e2e/release-journeys.spec.ts), run by [deploy-staging.yml](../../.github/workflows/deploy-staging.yml) | The customer, counter and admin journeys in a real browser against the staging site that was just deployed | The deployed staging site, its seeded accounts and the demonstration passwords held as secrets of the staging environment |

The browser tests in the pipeline run every journey twice, once in desktop
Chromium and once in a phone viewport 390 pixels wide. With
`E2E_REQUIRE_BACKEND=1`, which the pipeline sets, a journey that cannot reach
the API fails instead of skipping itself. The journeys write data, so they run
against staging and never against production.

The staging run records no trace and no video, because those would record the
passwords the journeys type. Staging runs on the real clock, so after closing
time the counter journey books two days ahead and the customer cancels it,
instead of checking a unit out for today. The same three journeys also run
against the local API on every pull request, so they are proven before they
reach staging.

## When each test runs

| When | What runs | Workflow |
|---|---|---|
| Every push to any branch | Secret scan. Ruff, strict mypy over the application and the tools, the five layer contracts, and every backend test that needs no database. The frontend lint, the TypeScript check, the unit and component tests, and a check that the generated API types match the OpenAPI document | [ci-fast.yml](../../.github/workflows/ci-fast.yml) |
| Every pull request into `develop` or `main` | The branch policy. Migrations from an empty PostgreSQL 16. The whole backend suite against that database with the coverage gate. `pip-audit` and the npm audit. The production build. The browser and accessibility tests against the real API and a freshly seeded database | [ci-integration.yml](../../.github/workflows/ci-integration.yml) |
| Every merge into `develop` | The migrations and the seed against the staging database, the smoke test of the new revision and again through the staging site, the header and TLS check of the staging site, and then the customer, counter and admin journeys in a browser against it | [deploy-staging.yml](../../.github/workflows/deploy-staging.yml) |
| Every release tag | A check that the tag is well formed and on `main`, my approval, then the migrations, the candidate revision with no traffic, the smoke test of the candidate, the traffic shift, the smoke test through the production site and the header and TLS check of the production site | [deploy-production.yml](../../.github/workflows/deploy-production.yml) |

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
read every module of the application and fail if any code other than the
policy multiplies a rate or a late fee by a number of days. The first also
fails if anything but the policies and the VAT module scales an amount, which
holds the report's share of a hire charge to the policies.

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
| [test_admin_catalogue_race.py](../../backend/tests/integration/test_admin_catalogue_race.py) and [test_asset_register_race.py](../../backend/tests/integration/test_asset_register_race.py) | Two administrators create the same code or register the same tag at once | The unique constraint refuses the second, which is answered 422 on its field with nothing of its write kept |
| [test_staff_admin_race.py](../../backend/tests/integration/test_staff_admin_race.py) | Two administrators demote each other at once, and two step down at once | The business is never left without an active administrator |

Two things make the holds safe, and the tests prove both. The candidate units
are locked with `SELECT ... FOR UPDATE SKIP LOCKED`, so concurrent bookings take
different units. The `daterange` exclusion constraint on active allocations has
the last word, and a violation becomes a clean 409 and never a 500.

The same tests also prove that a failure leaves nothing behind.
[test_checkout_transaction.py](../../backend/tests/integration/test_checkout_transaction.py),
[test_return_transaction.py](../../backend/tests/integration/test_return_transaction.py),
[test_charge_correction_transaction.py](../../backend/tests/integration/test_charge_correction_transaction.py)
and
[test_asset_register_transaction.py](../../backend/tests/integration/test_asset_register_transaction.py)
make each write fail at its audit event or at the commit, and find that nothing
was kept.

## Results

These are the figures of the release, from the release hardening pull request,
[#60](https://github.com/teon-artilionAI/toolshed-hire/pull/60), the last change
before `v0.4.0` on 4 October 2026. The hotfixes `v0.4.1` and `v0.4.2` the same
afternoon added five backend tests and fifteen frontend tests, and the rest of
the table holds for them too. What testing by hand found is under
[Testing the release by hand](#testing-the-release-by-hand).

| Check | Result |
|---|---|
| Backend tests | 4,618 passed on PostgreSQL 16 |
| Coverage of the domain and application layers | 100 percent of lines, against a floor of 70 |
| Ruff | Clean |
| mypy, strict | Clean on 341 source files |
| Layer import contracts | 5 kept |
| Frontend unit and component tests | 1,443 passed |
| Frontend lint and type check | Clean |
| Generated API types | Match the OpenAPI document |
| Production build | Clean |
| Browser and accessibility tests | 392 passed against the real API and a freshly seeded PostgreSQL in CI, none skipped |
| Accessibility | 109 axe scans across all 24 screens and their states, zero findings at any impact |
| Layout | Every screen at 360, 768 and 1440 pixels, nothing scrolls sideways |
| Journeys on staging | The customer, counter and admin journeys passed against the staging site, and run again after every staging deployment |
| Deployed headers and TLS | Passed on staging and on production |

How the suite grew is recorded in the "Manual verification" section of every
pull request, from 73 backend tests in the first one. The last eight read as
follows.

| Pull request | Backend tests | Frontend unit and component | Browser and accessibility |
|---|---|---|---|
| [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50) returns and settlement | 3,272 | 1,016 | 106 |
| [#51](https://github.com/teon-artilionAI/toolshed-hire/pull/51) damage and quarantine | 3,431 | 1,056 | 114 |
| [#55](https://github.com/teon-artilionAI/toolshed-hire/pull/55) reporting | 3,590 | 1,122 | 132 |
| [#56](https://github.com/teon-artilionAI/toolshed-hire/pull/56) admin operations | 3,879 | 1,200 | 152 |
| [#57](https://github.com/teon-artilionAI/toolshed-hire/pull/57) catalogue and pricing | 4,117 | 1,282 | 168 |
| [#58](https://github.com/teon-artilionAI/toolshed-hire/pull/58) asset register | 4,363 | 1,353 | 184 |
| [#59](https://github.com/teon-artilionAI/toolshed-hire/pull/59) staff accounts and customer holds | 4,594 | 1,438 | 202 |
| [#60](https://github.com/teon-artilionAI/toolshed-hire/pull/60) release hardening | 4,618 | 1,443 | 392 |
| [#64](https://github.com/teon-artilionAI/toolshed-hire/pull/64) hotfix 0.4.1 | 4,623 | 1,455 | 392 |
| [#69](https://github.com/teon-artilionAI/toolshed-hire/pull/69) hotfix 0.4.2 | 4,623 | 1,458 | 392 |

### Testing the release by hand

After `v0.4.0` was live I walked every role through a browser on a local copy
of the release, and the public pages on production. As a customer I searched,
booked and opened my bookings and account. At the counter I booked for a
customer, checked the unit out, took it back, filed a damage report that
charged the customer, and read the settlement. As the owner I read the
dashboard and the report, resolved the damage report, reversed the recovery
charge and opened the audit trail, the users, the catalogue and the asset
register.

Every automated check was green, and the walk still found eight faults. None
lost data. Each told a person something wrong or made the first visit slower
than it had to be. They are listed in issue
[#63](https://github.com/teon-artilionAI/toolshed-hire/issues/63), and seven
are fixed in [#64](https://github.com/teon-artilionAI/toolshed-hire/pull/64),
released as `v0.4.1`.

- The browser gave up on a request after eight seconds, which a cold start can
  take longer than.
- The home page named the suburbs of the branches, not the branches.
- A booking already collected or back said nothing had been charged and to
  ring the branch to change it.
- The seeded customers were members since the day of the seed, with hire
  history from March and June.
- While a damage report was outstanding, the return showed a settlement table
  of noughts.
- A settled hire did not say when a correction had since given money back.
- The diary wrote a booked return date in words that read like the day the unit
  came back.
- Stored charge descriptions write money as R300.00, where the screens write
  R 300.00. This one is left on purpose. The whole backend writes it that way
  and production already holds those rows, so changing one line would leave
  the history in two formats.

Three more turned up while I fixed these, and are fixed in the same release.
Reading the staging pipeline showed that a failed journey uploaded a report
folder the run never writes. A test written for the settlement fix found a
reversed late fee shown under its unit as a second charge with a minus sign.
The first pipeline run of the fix showed that the release journey only passed
before half past ten, because the API's clock is pinned to 10:00 and the
journey counted down on the browser's real clock. Each fix to a screen or to
the seed has a test that fails without it. The longer timeout and the pipeline
changes have none, and I checked them by running them.

Then I tested `v0.4.1` the same way on production, signed in as the customer
and as the owner. The customer searched, booked, held and confirmed a unit,
found it under My Hires and cancelled it. At the Cape Town CBD counter the
owner booked a unit for the trade customer, checked it out and took it back,
and the deposit was released in full. The owner's screens, the September
report and the worked example read as they should. One fault turned up. A
cancellation reason that ended in a full stop read with a second full stop
after the closing quote. It is issue
[#68](https://github.com/teon-artilionAI/toolshed-hire/issues/68), fixed in
[#69](https://github.com/teon-artilionAI/toolshed-hire/pull/69) and released
as `v0.4.2`.

### Figures worked out by hand

The worked example from the Task 1 design document holds through the API and on
staging. A hire with a R1,200.00 deposit at a late fee of R120.00 a day, returned
two days late, has R240.00 withheld, R960.00 released and R0.00 due, and the
rental is settled. [test_returns.py](../../backend/tests/api/test_returns.py)
follows it through the routes, and
[test_rental_reads_like_the_worked_example.py](../../backend/tests/integration/test_rental_reads_like_the_worked_example.py)
compares a rental opened at the counter with the seeded one. Reversed by the
owner, it keeps R240.00 withheld and R960.00 released and adds a settled charge
of minus R240.00.

The damage path holds over HTTP in
[test_damage_journey.py](../../backend/tests/api/test_damage_journey.py). R1,200.00
is held, the unit comes back one grade worse and the deposit waits for the
assessment. A chargeable report recovers R450.00, which is R391.30 plus R58.70
VAT, so R450.00 is withheld, R750.00 released and R0.00 due.

The report is proved against a dataset I worked out by hand. Seven units across
two branches, with a retirement, a quarantine, a hire of several units, a late
fee, a recovery and a repair, are built by
[report_dataset.py](../../backend/tests/support/report_dataset.py), whose
docstring works every figure out.
[test_report_worked_dataset.py](../../backend/tests/integration/test_report_worked_dataset.py)
asserts every grouping, both filters, the totals and the dashboard against it.
It gives 40 days on hire over 128 serviceable days, which is 31.25 percent, and
R1,321.95 of gross contribution, and a shared hire charge of R725.25 splits as
R212.63, R212.63 and R299.99.

A price change never reaches a booking already made.
[test_rate_change_snapshot.py](../../backend/tests/integration/test_rate_change_snapshot.py)
books a model at R280 a day through HTTP, raises the rate to R310, and finds
the booking, its line and the rental checked out from it still at R280, while a
new quote and a new booking take R310.

The seed writes a season of trading history, 1,613 closed hires from June to
September 2026 at the three branches, with late returns and damage that was
resolved, so the report has real volume to read. The September 2026 report
shows about 20 to 24 percent utilisation at each branch.
[test_seed_trading_history.py](../../backend/tests/integration/test_seed_trading_history.py)
reads the season back from PostgreSQL and works every money figure out again
with the domain's own policies.

## Non-functional requirements

Each target is the one in the Task 1 design document, summed up in my own words.
The status says honestly how far I have verified it today.

| NFR | What it asks for | How I verify it today | Status |
|---|---|---|---|
| NFR-01 | A fast availability search on the deployment, with a set budget for server time | The search answers a whole page of models for every branch in a fixed number of statements, which [test_availability_list.py](../../backend/tests/integration/test_availability_list.py) counts. Its query plan ran in under a millisecond on the seeded fleet and in about two milliseconds at ten times the data when it was built. There is no load test against the deployed revision yet | Not yet verified on the deployment. The load test is planned for Task 3 |
| NFR-02 | The first request after an idle spell finishes within a set time, slow requests show progress, and no button is pressed twice | Every screen shows a loading state, and every write button is disabled while its request is in flight, which the component tests check. The smoke test allows for a cold start. The cold start I measured on production is in the [README](../../README.md#try-it-in-five-minutes) | Partly met |
| NFR-03 | Twenty concurrent holds for five units give five holds and fifteen clean refusals, and the write path is fast | [test_concurrent_holds.py](../../backend/tests/integration/test_concurrent_holds.py) on every pull request. The response time of the writes has not been measured on the deployment | Met for correctness. Speed not yet measured |
| NFR-04 | A year's report and its export finish within a set time | The report and the CSV take at most 366 days, are three statements whatever the size of the fleet, which [test_report_reads.py](../../backend/tests/integration/test_report_reads.py) counts, and the CSV is streamed a line at a time. The season of trading history gives the report real volume. Neither has been timed on the deployment | Partly met |
| NFR-05 | 99 percent availability over trading hours, measured by scheduled checks | No scheduled checks run. Only the deployment checks look at the health of the service. [deviations.md](deviations.md) says why | Not in place |
| NFR-06 | A dropped connection never leaves an operation half done, and a signed in assistant resumes without signing in again | The transaction tests fail a checkout, a return, a correction and a register write part way and find nothing kept. [session.spec.ts](../../frontend/e2e/session.spec.ts) shows a reload keeps the session. Cutting the database connection in the middle of a transaction, and the manual drill, are not done | Partly met |
| NFR-07 | HTTPS with HSTS, a strict Content Security Policy, a strict refresh cookie and tokens kept out of browser storage | The headers are in [vercel.json](../../frontend/vercel.json) and [security_headers.py](../../backend/app/api/security_headers.py), checked by [test_security_headers.py](../../backend/tests/api/test_security_headers.py). After every deployment [check-security-headers.sh](../../infra/scripts/check-security-headers.sh) checks the deployed headers, including HSTS of at least half a year (15,768,000 seconds), and the TLS floor. The browser tests run every screen under the same policy. [web-storage.test.ts](../../frontend/src/shared/web-storage.test.ts) proves no token reaches storage | Met |
| NFR-08 | Passwords of twelve characters or more, bcrypt at work factor 12, a lockout, and the same answer and timing for a wrong password and an unknown address | [test_login_lockout_window.py](../../backend/tests/api/test_login_lockout_window.py) and [test_login_throttle_and_timing.py](../../backend/tests/api/test_login_throttle_and_timing.py). The timing test counts one bcrypt check on every path and compares medians over five samples, not the hundred the design asks for. The hashing time on the Cloud Run instance has not been measured | Partly met |
| NFR-09 | No route without a declared policy, another customer's record answered 404, another branch's write answered 403 | The application refuses to start on a route with no policy. [test_route_policies.py](../../backend/tests/api/test_route_policies.py) enumerates the routes, the admin routes included, and holds the role matrix, and [test_ownership_and_branch_scope.py](../../backend/tests/api/test_ownership_and_branch_scope.py) covers ownership and branch scope | Met |
| NFR-10 | Every change writes its audit event in the same transaction, and the application cannot update or delete one | [test_application_role.py](../../backend/tests/integration/test_application_role.py) has an update, a delete and a truncate of the audit table refused for the application role, and [test_application_role_reads.py](../../backend/tests/integration/test_application_role_reads.py) has it read the audit trail and fail to change or remove one event by its number. The transaction tests show a failed audit write fails the operation | Met |
| NFR-11 | A walk-in booking and checkout within a set time after short training, proved in moderated sessions | The counter screens have one main action each, and every confirmation says in words what will happen and to which unit. No moderated sessions have been run | Planned before handover |
| NFR-12 | One problem format, no internal detail in an error, a conflict that names the model and dates, and an empty state on every list | Every error is a problem document. [test_plain_refusals.py](../../backend/tests/api/test_plain_refusals.py) fails on a rule identifier or a raw value in a message, [test_allocation_conflict_translation.py](../../backend/tests/integration/test_allocation_conflict_translation.py) proves a constraint violation is a 409, every list has an empty state, and the screens no longer promise an email this demonstration cannot deliver | Met |
| NFR-13 | WCAG 2.2 AA on all 24 screens, 44 pixel targets, keyboard use, and layouts from 360 pixels wide | On every pull request, 109 axe scans across all 24 screens and their states, with each screen opened as the role it belongs to, report zero findings at any impact, and a serious or critical one fails the build. The layout sweep opens every screen at 360, 768 and 1440 pixels and finds nothing that scrolls sideways. The keyboard and screen reader passes by hand are not recorded yet | Mostly met |
| NFR-14 | Layer boundaries, no type errors, low complexity, short files and a coverage floor, all blocking a merge | The five contracts, strict mypy, the TypeScript check with strict mode set explicitly, a lint rule that bans `any` in the frontend, Ruff with a complexity limit of 10 and the coverage floor block every merge. Nine application source files are between 302 and 315 lines, a little over the 300 line guide, which no check enforces | Mostly met |
| NFR-15 | The searches and reports hold at ten times the fleet, on indexed paths, within the connection ceiling | Planner tests prove each counter read, the customer search, the report, the two logs, the catalogue and the register use their indexes, for example [test_counter_read_indexes.py](../../backend/tests/integration/test_counter_read_indexes.py), [test_report_reads.py](../../backend/tests/integration/test_report_reads.py) and [test_asset_register_indexes.py](../../backend/tests/integration/test_asset_register_indexes.py). No volume test at the stated row counts has been run, and the instance cap is one, not four | Partly met |
| NFR-16 | Only the last four characters of an identity document, no card data, a privacy notice, and a customer can export and correct their own data | The schema has no column for a full document number or a card. The privacy notice is at `/privacy`. A customer corrects their own details on SC-09. Export, the retention period, anonymisation and the breach procedure are not built | Partly met |
| NFR-17 | Where personal information is held is recorded and disclosed, and no customer data leaves in logs or pipeline artifacts | The privacy notice names Neon and Google Cloud in London, Vercel and Resend. Search text is logged by its length only, and secrets are redacted from every log line. The register of processing and an automated check of pipeline artifacts are not done | Partly met |
| NFR-18 | Structured logs, a health check, migrations that apply forward, a fast rollback and a tested restore | Every log line is JSON with the request id, route, role and outcome, checked by [test_access_log.py](../../backend/tests/api/test_access_log.py) and [test_log_redaction.py](../../backend/tests/unit/test_log_redaction.py). The health check reports the database and the revision. Migrations run from empty on every pull request and over the seeded staging database on every merge. Rollback is written up in [OPERATIONS.md](../../infra/OPERATIONS.md). The rollback rehearsal and the restore drill are not done yet | Partly met |

The checks the design keeps for a release that are still open are the load test
and the volume test. The checks it keeps for handover, which are the usability
sessions, the interruption drill, the privacy review, the rollback rehearsal
and the restore drill, are the main work left on this table for Task 3.
