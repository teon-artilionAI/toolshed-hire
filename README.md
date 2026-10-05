<p align="center">
  <img src="docs/task1/assets/toolshed-hire-logo.png" alt="Toolshed Hire" width="260">
</p>

# Toolshed Hire

[![Fast checks](https://github.com/teon-artilionAI/toolshed-hire/actions/workflows/ci-fast.yml/badge.svg?branch=develop)](https://github.com/teon-artilionAI/toolshed-hire/actions/workflows/ci-fast.yml)
[![Deploy to staging](https://github.com/teon-artilionAI/toolshed-hire/actions/workflows/deploy-staging.yml/badge.svg)](https://github.com/teon-artilionAI/toolshed-hire/actions/workflows/deploy-staging.yml)
[![Deploy to production](https://github.com/teon-artilionAI/toolshed-hire/actions/workflows/deploy-production.yml/badge.svg)](https://github.com/teon-artilionAI/toolshed-hire/actions/workflows/deploy-production.yml)

Toolshed Hire is a rental management system for a fictional tool and equipment
hire business with three branches in Cape Town, which today runs on a paper
diary and a WhatsApp group. A customer checks availability at all three
branches at once and books named units online. Counter staff book walk-ins,
hand equipment over, take it back and settle the deposit, and the database
itself refuses to promise one unit to two hires. The owner keeps the catalogue,
the prices, the fleet and the staff accounts, and sees which equipment earns
its keep.

This repository holds Task 2 of my INSY7315 Work Integrated Learning project,
which is the built system. I am Teon Kleynhans, ST10434209, and I work on it
alone.

## Links

| What | Where |
|---|---|
| Live system | <https://toolshed-hire.vercel.app> |
| Staging | <https://toolshed-hire-staging.vercel.app> |
| Recorded presentation | Handed in on ARC with the link to this repository, as agreed with my lecturer. |
| Slides | [toolshed-hire-task-2.pdf](docs/task2/slides/toolshed-hire-task-2.pdf). The outline and the demonstration script are in [presentation.md](docs/task2/presentation.md). |
| Task 1 design document | [INSY7315_Task1_ToolshedHire.pdf](docs/task1/INSY7315_Task1_ToolshedHire.pdf) |
| Task 2 evidence | [docs/task2](docs/task2/README.md) |

## Demo login

| Role | Email | Password |
|---|---|---|
| Customer | `w.adonis@buildright.co.za` | `Hire-UQdzV8RMo50z` |

The counter staff and admin logins are never published in this repository. They
are handed in on ARC with the recorded presentation.

## Try it in five minutes

These steps are for the demo customer on the live system.

1. Open <https://toolshed-hire.vercel.app>. The catalogue home (SC-01) needs no
   account. Pick a start date from tomorrow onwards and an end date, and search.
2. The results (SC-02) say for every model whether each branch has one free for
   those dates. Choose a branch to narrow the list.
3. Open a model (SC-03). The rates, the deposit and the late fee are on the
   page. The price on the booking card is the server's quote for the dates and
   the quantity. Add it to the hire basket.
4. Open the basket (SC-04) and review it. The site asks you to sign in with the
   demo login and then brings you back.
5. The review shows the server's figures. Hold sets named units aside for thirty
   minutes with a countdown. Confirm gives you a booking reference. The screen
   does not promise an email, because this demonstration only delivers email to
   my own address.
6. My Hires (SC-07) lists the booking. Open it (SC-08) and cancel it, so the
   units go back on the shelf for the next person.
7. Account (SC-09) shows the profile and the hire history, newest first. The
   oldest hire, `TSH-H-26-000098` from March 2026 on the last page, is the
   worked example from the Task 1 design document. Its R1,200.00 deposit was
   held, R240.00 was kept for two days late at R120.00 a day, R960.00 was
   returned and nothing was left to pay.
8. While signed in as the customer, open `/counter`. The screen refuses, and the
   API would refuse as well.

The recorded presentation shows the other two roles on the same production
system.

- A counter assistant at Cape Town CBD reads the day's dashboard, registers a
  walk-in, books one unit for today, checks it out with the deposit taken and
  takes it back with the deposit released. They find a unit at any branch by
  its tag and open the worked example by its reference.
- The owner signs in as the administrator and reads the dashboard of the whole
  business (SC-19). They run the utilisation and gross contribution report for
  September 2026 by branch (SC-22), where each branch shows about 20 to 24
  percent from the season of trading history the seed writes, and download it
  as CSV. On the catalogue (SC-20) they change a daily rate, and the screen says
  before saving that bookings already made keep the rate they were booked at.
  On the asset register (SC-21) they register a unit, commission it and retire
  it with a reason, and it stays in the register with its history. On users
  (SC-23) they open a counter staff account without anyone seeing a password,
  and deactivate it with a reason. Last, the audit trail (SC-24) shows each of
  those changes, who made it and the values before and after.

The API scales down to nothing when it is idle and the database suspends after
five minutes without a query, so both are asleep when nobody has used the site
for a while. The first request after a quiet spell wakes them and takes about six
seconds. I measured 5.9 seconds on production on the morning of 4 October 2026
after the site had been idle overnight, and between 0.26 and 0.6 seconds for
the requests that followed. A loading state shows while it waits. The browser
waits up to fifteen seconds for an answer and tries a read again if the first
try runs out of time, and the API starts with start up CPU boost to shorten
the wait.

## What each task delivered

| Task | What I delivered | Where it is |
|---|---|---|
| Task 1 | The design document, submitted on 16 August 2026, with the requirements, the design, security, the pipeline, the running costs and change management. A clickable prototype of all 24 screens on sample data, and a walking skeleton of the API. | [The Task 1 design document](docs/task1/INSY7315_Task1_ToolshedHire.pdf), and the baseline in [CHANGELOG.md](CHANGELOG.md) |
| Task 2 | This system, released as `v0.4.0` with the fixes from testing it by hand in `v0.4.1` and `v0.4.2`, and marked by the tag `task2-v1.0`. All 24 screens on a real API and database, hosting in two environments, the GitHub workflow and pipeline, and the recorded presentation. | This README and [docs/task2](docs/task2/README.md) |
| Task 3 | To come. The final release `v1.0.0`, the report and the user guide, and the work listed under [Known limitations](#known-limitations). | |

This table says where to find the evidence for each part of Task 2.

| Part of Task 2 | Where to look |
|---|---|
| Look and feel, branding | The live system, the [slides](docs/task2/slides/toolshed-hire-task-2.pdf), and the colours, type and contrast notes in [tailwind.config.js](frontend/tailwind.config.js) |
| Usability and feedback | [frontend/README.md](frontend/README.md), under Shared states, Booking a hire and each screen's section |
| Responsive design and accessibility | [accessibility.spec.ts](frontend/e2e/accessibility.spec.ts), [accessibility-states.spec.ts](frontend/e2e/accessibility-states.spec.ts), [narrow-screens.spec.ts](frontend/e2e/narrow-screens.spec.ts), NFR-13 in the [test plan](docs/task2/test-plan-and-results.md) |
| Back-end code and design patterns | [Architecture](#architecture) below, and [backend/README.md](backend/README.md) |
| Database | [The schema](backend/README.md#the-schema), [the constraint](backend/README.md#the-constraint), [alembic/versions](backend/alembic/versions) |
| APIs | [Endpoints](backend/README.md#endpoints), and the OpenAPI document [openapi.json](backend/openapi.json) |
| Security | [security-controls.md](docs/task2/security-controls.md) |
| Business logic and data flow | [Requirements traceability](#requirements-traceability) below, and the reservation lifecycle in [backend/README.md](backend/README.md#the-reservation-lifecycle) |
| Hosting and connectivity | The live links above, [infra/SETUP.md](infra/SETUP.md) and [infra/OPERATIONS.md](infra/OPERATIONS.md) |
| Stability and the reasons for each choice | [infra/SETUP.md](infra/SETUP.md), [deviations.md](docs/task2/deviations.md) |
| Branching and workflow | [CONTRIBUTING.md](CONTRIBUTING.md), the [merged pull requests](https://github.com/teon-artilionAI/toolshed-hire/pulls?q=is%3Apr+is%3Amerged) |
| Automated tests and deployment | [Pipeline and branching](#pipeline-and-branching) below, and [test-plan-and-results.md](docs/task2/test-plan-and-results.md) |
| Presentation | The recording, handed in on ARC, and [presentation.md](docs/task2/presentation.md) |

## Requirements traceability

Each functional requirement from the Task 1 design document, in a few words of
my own, as it stands in the `v0.4.0` release on 4 October 2026. Twenty seven
are built and one is partly built. Every issue names the requirements it
covers, and every branch and pull request carries its issue number.

| FR | Requirement | Status | Branch and pull request | Screens | Tests that prove it |
|---|---|---|---|---|---|
| FR-01 | Register, verify an email, sign in, reset a password, edit own details | Built | 007 [#40](https://github.com/teon-artilionAI/toolshed-hire/pull/40), 008 [#41](https://github.com/teon-artilionAI/toolshed-hire/pull/41), 011 [#46](https://github.com/teon-artilionAI/toolshed-hire/pull/46) | SC-05, SC-06, SC-09 | [test_register.py](backend/tests/api/test_register.py), [test_password_reset.py](backend/tests/api/test_password_reset.py), [account.spec.ts](frontend/e2e/account.spec.ts) |
| FR-02 | Public catalogue with rates, deposit and hire limits | Built | 006 [#39](https://github.com/teon-artilionAI/toolshed-hire/pull/39) | SC-01, SC-03 | [test_catalogue_browse.py](backend/tests/api/test_catalogue_browse.py), [catalogue.spec.ts](frontend/e2e/catalogue.spec.ts) |
| FR-03 | One search says per branch whether a model is free | Built | 006 [#39](https://github.com/teon-artilionAI/toolshed-hire/pull/39) | SC-02, SC-03 | [test_availability_search.py](backend/tests/integration/test_availability_search.py), [test_availability_list.py](backend/tests/integration/test_availability_list.py) |
| FR-04 | Units out of service are never offered | Built | 006 [#39](https://github.com/teon-artilionAI/toolshed-hire/pull/39), 015 [#51](https://github.com/teon-artilionAI/toolshed-hire/pull/51) | SC-02, SC-03 | [test_availability_search.py](backend/tests/integration/test_availability_search.py), [test_damage_and_quarantine.py](backend/tests/integration/test_damage_and_quarantine.py), [test_asset_register_transaction.py](backend/tests/integration/test_asset_register_transaction.py) |
| FR-05 | Several models, one period, one branch, priced before commitment | Built | 009 [#42](https://github.com/teon-artilionAI/toolshed-hire/pull/42), 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43) | SC-03, SC-04 | [test_quote.py](backend/tests/api/test_quote.py), [test_reservation_routes.py](backend/tests/api/test_reservation_routes.py), [reservation-changes.spec.ts](frontend/e2e/reservation-changes.spec.ts) |
| FR-06 | Named units on every line, never a count | Built | 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43) | SC-04, SC-13 | [test_hold_all_or_nothing.py](backend/tests/unit/test_hold_all_or_nothing.py), [test_concurrent_allocation.py](backend/tests/integration/test_concurrent_allocation.py) |
| FR-07 | No unit ever holds two overlapping bookings | Built | 002 [#24](https://github.com/teon-artilionAI/toolshed-hire/pull/24), 005 [#38](https://github.com/teon-artilionAI/toolshed-hire/pull/38) | SC-04, SC-13 | [test_exclusion_constraint.py](backend/tests/integration/test_exclusion_constraint.py), [test_concurrent_holds.py](backend/tests/integration/test_concurrent_holds.py) |
| FR-08 | Thirty minute hold that lapses by itself | Built | 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43) | SC-04 | [test_expire_holds_sweep.py](backend/tests/unit/test_expire_holds_sweep.py), [test_hold_expiry_sweep.py](backend/tests/integration/test_hold_expiry_sweep.py) |
| FR-09 | Confirm only when fully allocated and the email is verified | Built | 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43) | SC-04, SC-13 | [test_confirm_reservation_use_case.py](backend/tests/unit/test_confirm_reservation_use_case.py), [test_reservation_states.py](backend/tests/unit/test_reservation_states.py) |
| FR-10 | Confirmation email with its delivery outcome recorded | Built | 005 [#38](https://github.com/teon-artilionAI/toolshed-hire/pull/38), 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43) | SC-04 | [test_notification_outbox.py](backend/tests/integration/test_notification_outbox.py), [test_resend_adapter.py](backend/tests/unit/test_resend_adapter.py) |
| FR-11 | See own bookings and cancel a held or confirmed one | Built | 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43) | SC-07, SC-08 | [test_cancellation_transaction.py](backend/tests/integration/test_cancellation_transaction.py), [reservation.spec.ts](frontend/e2e/reservation.spec.ts) |
| FR-12 | An uncollected booking becomes a no show with a strike | Built | 013 [#48](https://github.com/teon-artilionAI/toolshed-hire/pull/48) | SC-11 | [test_no_show_sweep.py](backend/tests/integration/test_no_show_sweep.py), [test_no_show_races.py](backend/tests/integration/test_no_show_races.py) |
| FR-13 | Find a customer, register a walk-in with no login | Built | 012 [#47](https://github.com/teon-artilionAI/toolshed-hire/pull/47) | SC-12 | [test_customer_lookup.py](backend/tests/api/test_customer_lookup.py), [test_walk_in.py](backend/tests/api/test_walk_in.py) |
| FR-14 | Same-day counter booking through the online path | Built | 012 [#47](https://github.com/teon-artilionAI/toolshed-hire/pull/47) | SC-13 | [test_counter_bookings.py](backend/tests/api/test_counter_bookings.py), [counter.spec.ts](frontend/e2e/counter.spec.ts) |
| FR-15 | Find any unit by tag at any branch, read only | Built | 013 [#48](https://github.com/teon-artilionAI/toolshed-hire/pull/48) | SC-17 | [test_asset_locator.py](backend/tests/api/test_asset_locator.py), [counter-overview.spec.ts](frontend/e2e/counter-overview.spec.ts) |
| FR-16 | Today's dashboard and a diary for any date | Built | 013 [#48](https://github.com/teon-artilionAI/toolshed-hire/pull/48) | SC-10, SC-11 | [test_counter_dashboard.py](backend/tests/api/test_counter_dashboard.py), [test_counter_diary.py](backend/tests/api/test_counter_diary.py) |
| FR-17 | Checkout per unit with the deposit taken | Built | 012 [#47](https://github.com/teon-artilionAI/toolshed-hire/pull/47) | SC-14 | [test_checkout_transaction.py](backend/tests/integration/test_checkout_transaction.py), [test_checkout_race.py](backend/tests/integration/test_checkout_race.py) |
| FR-18 | Returns item by item until the last one is back | Built | 014 [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50) | SC-15 | [test_return_rules.py](backend/tests/unit/test_return_rules.py), [test_return_transaction.py](backend/tests/integration/test_return_transaction.py) |
| FR-19 | One late fee policy that staff confirm and cannot set | Built | 014 [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50) | SC-15, SC-18 | [test_late_fee_policy.py](backend/tests/unit/test_late_fee_policy.py), [test_one_place_for_a_late_fee.py](backend/tests/unit/test_one_place_for_a_late_fee.py) |
| FR-20 | Damage report with an explicit charge decision, quarantine and resolution | Built | 015 [#51](https://github.com/teon-artilionAI/toolshed-hire/pull/51) | SC-15, SC-16, SC-21 | [test_damage_and_quarantine.py](backend/tests/integration/test_damage_and_quarantine.py), [test_damage_journey.py](backend/tests/api/test_damage_journey.py), [counter.spec.ts](frontend/e2e/counter.spec.ts) |
| FR-21 | Deposit settled at return, the rest released, a shortfall carried | Built | 014 [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50) | SC-15 | [test_deposit_settlement.py](backend/tests/unit/test_deposit_settlement.py), [test_returns.py](backend/tests/api/test_returns.py), [test_loss_and_balance.py](backend/tests/api/test_loss_and_balance.py) |
| FR-22 | Catalogue and prices kept once, bookings keep their prices | Built | 010 [#43](https://github.com/teon-artilionAI/toolshed-hire/pull/43), 019 [#57](https://github.com/teon-artilionAI/toolshed-hire/pull/57) | SC-20 | [test_rate_change_snapshot.py](backend/tests/integration/test_rate_change_snapshot.py), [test_admin_models.py](backend/tests/api/test_admin_models.py), [admin-catalogue.spec.ts](frontend/e2e/admin-catalogue.spec.ts) |
| FR-23 | Asset register and lifecycle, no retirement while booked | Built | 012 [#47](https://github.com/teon-artilionAI/toolshed-hire/pull/47), 020 [#58](https://github.com/teon-artilionAI/toolshed-hire/pull/58) | SC-21 | [test_asset_transitions.py](backend/tests/unit/test_asset_transitions.py), [test_asset_register_transaction.py](backend/tests/integration/test_asset_register_transaction.py), [admin-assets.spec.ts](frontend/e2e/admin-assets.spec.ts) |
| FR-24 | Utilisation and gross contribution with export | Built | 017 [#55](https://github.com/teon-artilionAI/toolshed-hire/pull/55) | SC-19, SC-22 | [test_report_worked_dataset.py](backend/tests/integration/test_report_worked_dataset.py), [test_admin_report_csv_and_dashboard.py](backend/tests/api/test_admin_report_csv_and_dashboard.py), [reporting.spec.ts](frontend/e2e/reporting.spec.ts) |
| FR-25 | Staff accounts and roles, deny by default | Built | 007 [#40](https://github.com/teon-artilionAI/toolshed-hire/pull/40), 021 [#59](https://github.com/teon-artilionAI/toolshed-hire/pull/59) | SC-23 | [test_route_policies.py](backend/tests/api/test_route_policies.py), [test_admin_users.py](backend/tests/api/test_admin_users.py), [test_staff_admin_race.py](backend/tests/integration/test_staff_admin_race.py), [admin-users.spec.ts](frontend/e2e/admin-users.spec.ts) |
| FR-26 | Append-only log of every change, readable by the owner | Built | 003 [#25](https://github.com/teon-artilionAI/toolshed-hire/pull/25), 005 [#38](https://github.com/teon-artilionAI/toolshed-hire/pull/38), 018 [#56](https://github.com/teon-artilionAI/toolshed-hire/pull/56) | SC-24 | [test_application_role.py](backend/tests/integration/test_application_role.py), [test_admin_audit_log.py](backend/tests/api/test_admin_audit_log.py), [admin-operations.spec.ts](frontend/e2e/admin-operations.spec.ts) |
| FR-27 | Waive, adjust or reverse a charge with a reason, never edit a settled one | Built | 014 [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50), 018 [#56](https://github.com/teon-artilionAI/toolshed-hire/pull/56) | SC-15, SC-24 | [test_settled_charge_guard.py](backend/tests/unit/test_settled_charge_guard.py), [test_charge_correction_transaction.py](backend/tests/integration/test_charge_correction_transaction.py), [test_settled_hire_corrections.py](backend/tests/integration/test_settled_hire_corrections.py) |
| FR-28 | Own charges, deposit position and a statement | Partly built. Hires, charges and the deposit position are on SC-09. The statement download is planned for Task 3. | 014 [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50) | SC-09 | [test_rental_lists.py](backend/tests/api/test_rental_lists.py), [SC09-Hire-History.test.tsx](frontend/src/features/customer/SC09-Hire-History.test.tsx) |

The non-functional requirements NFR-01 to NFR-18 are mapped to how I verify
each one in [test-plan-and-results.md](docs/task2/test-plan-and-results.md).

## Architecture

The backend is FastAPI on Python 3.12 with SQLModel and PostgreSQL 16. The
frontend is React 19 with TypeScript, Vite and Tailwind CSS.

| Layer | Folder | Holds |
|---|---|---|
| Domain | [app/domain](backend/app/domain) | The business rules as plain classes. No framework, no SQL, no input or output. |
| Application | [app/application](backend/app/application) | One use case per action, the transaction boundary, and the ports it works through. |
| Infrastructure | [app/infrastructure](backend/app/infrastructure) | The SQL repositories, the unit of work, the clock, hashing and the email adapter. |
| API | [app/api](backend/app/api) | Routers, request and response schemas, access policies, and the composition root that wires the rest together. |

The eight modules of the design keep the same name in every layer they appear
in, and all eight are built.

| Module | Covers |
|---|---|
| `identity` | Accounts, sessions, customers and walk-ins, staff accounts and customer holds |
| `catalogue` | Categories, models and their prices, the asset register and the asset locator |
| `availability` | The free or not free search and the allocation of named units |
| `booking` | Reservations, their eight states, no shows, the force release and the reallocation |
| `hire` | Checkout, rentals, returns, losses, damage, deposit settlement and charge corrections |
| `money` | `Money`, VAT, the pricing policy and quotes |
| `notification` | The outbox, the email gateway, the notification log and the re-send |
| `reporting` | Utilisation, gross contribution and the owner's dashboard |

### The request path

```mermaid
flowchart LR
    browser["Browser<br/>React app"] -->|"HTTPS, one origin"| vercel["Vercel<br/>static bundle and /api rewrite"]
    vercel -->|"/api, server side"| api["Google Cloud Run<br/>FastAPI API, London"]
    api -->|"pooled connection, verified TLS"| db[("Neon PostgreSQL 16<br/>London")]
    api -->|"after the commit"| resend["Resend<br/>email"]
    secrets["Secret Manager"] -.->|"read at start"| api
```

The browser only ever talks to the site's own address. Vercel serves the built
bundle and rewrites every `/api` request to Cloud Run on the server side, so the
refresh cookie stays on one origin and the Content Security Policy can allow
`connect-src 'self'` and nothing else. The API reads its secrets from Secret
Manager, connects to the database as a restricted role that cannot rewrite the
audit trail, and sends email through Resend once the transaction has committed.

### The four design patterns

| Pattern | Where | What it does here |
|---|---|---|
| Repository with Unit of Work | [application/unit_of_work.py](backend/app/application/unit_of_work.py), [infrastructure/unit_of_work.py](backend/app/infrastructure/unit_of_work.py), for example [SqlAssetRepository](backend/app/infrastructure/availability.py) and [SqlReservationRepository](backend/app/infrastructure/booking.py) | A hold writes allocations, a new status and an audit event. One unit of work owns that transaction, so all of it commits or none of it does. |
| Adapter | [application/notification/ports.py](backend/app/application/notification/ports.py), [infrastructure/notification](backend/app/infrastructure/notification) | `NotificationGateway` is the port and `ResendEmailAdapter` is the only class that knows which provider sends the email. A failed send never rolls a booking back. |
| Strategy | [domain/policies](backend/app/domain/policies) | `PricingPolicy` and `LateFeePolicy`, each with a standard implementation and a fixed one for tests, and the share of a whole hire charge that the report gives each unit. A test reads every module to prove no other code works out a price, a late fee or a share. |
| State | [domain/states](backend/app/domain/states) | The eight reservation states. The base state refuses every move, and each state allows only the moves that are legal from it. |

### Why the layers are enforced

The rules that make this system worth having live in the domain layer. One
import of a database driver or a framework into it would make those rules
impossible to test without a database, and the fast tests would stop being
fast. So I do not rely on discipline. `lint-imports` checks five contracts in
[pyproject.toml](backend/pyproject.toml) on every push, and a broken contract
fails the build. The domain imports nothing from the other layers, the
application layer imports neither the API nor the infrastructure, the
infrastructure does not import the API, and neither inner layer imports
SQLAlchemy, FastAPI, pydantic or any driver. The use cases depend on ports, and
`app/api` is the only place that decides which implementation stands behind each
one.

## Pipeline and branching

| Workflow | Runs on | What it does |
|---|---|---|
| [ci-fast.yml](.github/workflows/ci-fast.yml) | Every push to every branch | Secret scan, Ruff, strict mypy, the layer contracts, the backend tests that need no database, the frontend lint, type check and unit tests, and a check that the generated API types are current |
| [ci-integration.yml](.github/workflows/ci-integration.yml) | Every pull request into `develop` or `main` | The branch policy, migrations from an empty PostgreSQL 16, the whole backend suite with the coverage gate, the dependency audits, the production build, and the browser and accessibility tests against the real API and a seeded database |
| [deploy-staging.yml](.github/workflows/deploy-staging.yml) | Every merge into `develop` | Builds the image by digest, migrates and seeds the staging database, deploys the API and the frontend, smoke tests the API directly and through the site, checks the deployed security headers and TLS, and then runs the customer, counter and admin journeys in a browser against the staging site |
| [deploy-production.yml](.github/workflows/deploy-production.yml) | A `vX.Y.Z` tag on `main` | Checks the tag, waits for my approval, then deploys the new API revision with no traffic, smoke tests it, shifts the traffic, deploys the frontend and checks the deployed security headers and TLS |

Each check workflow ends in one outcome job, and the two outcome jobs,
"Fast checks outcome" and "Integration outcome", are the required checks on
`main` and `develop`.

### Branches

I use a reduced GitFlow, written out in [CONTRIBUTING.md](CONTRIBUTING.md).
Every change starts as an issue, and its branch is `feature/nnn-slug`,
`docs/nnn-slug` or `test/nnn-slug`, cut from `develop`, where `nnn` is the issue
number. A ruleset protects `main` and `develop`. Nothing reaches them without a
pull request, both required checks passing on an up to date branch and every
review thread resolved. Force pushes and deletion are blocked, merge commits are
the only merge method, and nobody can bypass the rules, me included. A second
ruleset stops a release or submission tag from being moved or deleted. The
integration workflow also refuses a pull request into `main` from anything but a
`release/` or `hotfix/` branch.

### Releases and environments

1. I check `develop` on staging.
2. I cut a release branch from `develop`, merge `main` into it, bump the
   versions and move the changelog entries under the new version.
3. I open a pull request into `main` that lists the issues it closes, and merge
   it once the checks pass.
4. I put an annotated tag `vX.Y.Z` on the merge commit. The tag starts the
   production deployment, which waits for my approval.
5. I open a pull request from `main` back into `develop`.

A fix to a released state goes the other way. A hotfix branch is cut from
`main`, merged into `main` through a pull request and tagged in the same way,
and then the hotfix branch, carrying the release merge commit, is merged into
`develop`. `v0.4.1` and `v0.4.2` went out like that.

| Release | Date | Release branch | What it added |
|---|---|---|---|
| `v0.1.0` | 2 October 2026 | `release/0.1.0` | The branch model and checks, the documented schema, the seeded fleet and the first deployment |
| `v0.2.0` | 2 October 2026 | `release/0.2.0` | The customer journey, sessions and roles, and the pricing policy |
| `v0.3.0` | 3 October 2026 | `release/0.3.0` | Registration and the counter journey, from a walk-in to the return, the deposit and damage (011 to 015) |
| `v0.4.0` | 4 October 2026 | `release/task-2` | The owner's side, reporting, the audit trail and corrections, the catalogue, the asset register and users (017 to 021), the hardening (022) and this evidence (016) |
| `v0.4.1` | 4 October 2026 | `hotfix/063-browser-test-fixes` | The fixes from testing `v0.4.0` by hand in a browser as each role (#63) |
| `v0.4.2` | 4 October 2026 | `hotfix/068-cancel-reason-full-stop` | A fix found by testing `v0.4.1` by hand on production (#68) |

The tag `task2-v1.0` marks the state I hand in for Task 2 and deploys nothing.
`v1.0.0` is kept for the release in Task 3 where the built system matches the
whole design.

| | Staging | Production |
|---|---|---|
| Site | <https://toolshed-hire-staging.vercel.app> | <https://toolshed-hire.vercel.app> |
| Deployed by | A merge into `develop` | A `vX.Y.Z` tag on `main`, after my approval |
| Database | Neon branch `staging` | Neon branch `main` |
| New revision | Takes traffic directly | Deployed with no traffic, smoke tested on its own address, then given the traffic |
| Checked after it | Smoke test, headers and TLS, and the three journeys in a browser | Smoke test, headers and TLS |
| Instances | At most one | At most one while it runs as a demonstration |

```mermaid
flowchart TD
    issue["Issue nnn"] --> feature["feature/nnn-slug from develop"]
    feature -->|"every push"| fast["Fast checks"]
    feature --> pr["Pull request into develop"]
    pr -->|"every pull request"| integration["Integration checks"]
    integration -->|"merge commit"| develop["develop"]
    develop -->|"deploy-staging.yml"| staging["Staging, then headers, TLS and browser journeys"]
    develop --> release["Release branch"]
    release -->|"pull request and checks"| main["main"]
    main --> tag["Annotated tag vX.Y.Z"]
    tag -->|"deploy-production.yml"| verify["Check the tag"]
    verify --> approve["My approval"]
    approve --> candidate["Candidate revision, no traffic"]
    candidate --> smoke["Smoke test the candidate"]
    smoke --> shift["Shift traffic, deploy the frontend"]
    shift --> production["Production, then headers and TLS"]
    main -->|"pull request back"| develop
```

The steps of a deployment, rollback, costs and tearing it all down are in
[infra/OPERATIONS.md](infra/OPERATIONS.md). How I set up the cloud accounts,
including the keyless deployment through Workload Identity Federation, is in
[infra/SETUP.md](infra/SETUP.md).

## Running it locally

I need Python 3.12, Node 22 and Docker.

```bash
# A local PostgreSQL 16 for the application
docker run --name tsh-pg -e POSTGRES_USER=toolshed -e POSTGRES_PASSWORD=toolshed \
  -e POSTGRES_DB=toolshed -p 5432:5432 -d postgres:16

cd backend
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\Activate.ps1 in PowerShell
pip install --editable ".[dev]"
cp .env.example .env
alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

The frontend runs in a second terminal.

```bash
cd frontend
npm ci
npm run dev
```

The site is on <http://localhost:5173>, and Vite sends `/api` to the API on port
8000, the same single origin the deployed site has. The tests marked `postgres`
empty every table, so they get their own database from
[docker-compose.yml](docker-compose.yml). [backend/README.md](backend/README.md)
and [frontend/README.md](frontend/README.md) have every other command.

## Known limitations

- Email is restricted to my own address on this demonstration, so a new
  customer cannot follow a verification link and a new member of staff cannot
  follow the link to choose a password. A counter assistant confirming a
  booking meets the verified email rule. The screens say plainly when an email
  cannot be delivered, and the notification is recorded as failed.
- The first request after a quiet spell is slow, as described above.
- A unit out on hire is not offered for a later period until it comes back,
  because only units on the shelf can be allocated.
- Every day is a trading day from 07:00 to 17:00. The earlier close on a
  Saturday and the Sunday closure are not modelled yet.
- There is no damage photograph upload yet, and no statement download or data
  export for a customer. Only the owner can send a failed confirmation again.
  The retention period in the privacy notice is not fixed.
- A six day hire costs more than a seven day one, because six days has no whole
  week to charge at the weekly rate. I built it as designed.
- When several people ask for more than one of the last few units of a model at
  once, all of them can be refused, and trying again works. Nobody is ever
  double booked.
- The report counts whole days and counts a charge in the period it was
  raised, and a unit the seed created already quarantined is out of service for
  the whole of any period, because no event records when it went there.
- A settled hire only takes a correction that gives money back, a deposit
  movement can be adjusted but not reversed, and the dashboard's count of
  failed emails keeps a failure that was sent again. A unit's history shows the
  newest fifty entries of each kind, and a length refusal from a request schema
  still shows the framework's own wording.
- Old `refresh_session` rows are never pruned, because the application's database role holds no DELETE on that table.
  The lazy sweep prunes old `rate_limit_counter` rows, but the refresh sessions need the operator job that
  [backend/README.md](backend/README.md#throttling) describes before real traffic.
- At a hundred times the data, the report degrades first, because it reads
  every unit and dated fact of a period into memory on each request, and then
  the audit trail, which counts every match on each page. The way out of each
  is in [backend/README.md](backend/README.md).
- From Dependabot I applied setuptools ([#32](https://github.com/teon-artilionAI/toolshed-hire/pull/32)), postcss ([#35](https://github.com/teon-artilionAI/toolshed-hire/pull/35)) and react-dom ([#36](https://github.com/teon-artilionAI/toolshed-hire/pull/36)).
  The majors of the GitHub Actions ([#29](https://github.com/teon-artilionAI/toolshed-hire/pull/29), [#30](https://github.com/teon-artilionAI/toolshed-hire/pull/30), [#31](https://github.com/teon-artilionAI/toolshed-hire/pull/31)), uvicorn ([#33](https://github.com/teon-artilionAI/toolshed-hire/pull/33)) and pydantic ([#34](https://github.com/teon-artilionAI/toolshed-hire/pull/34)) are deferred, each with its reason on its pull request.
  The Tailwind CSS 4 update ([#37](https://github.com/teon-artilionAI/toolshed-hire/pull/37)) is closed in favour of issue [#49](https://github.com/teon-artilionAI/toolshed-hire/issues/49), the planned move to Tailwind 4 that also retires the audit exception for `braces`.
- The load test, the volume test and the restore drill have not been run
  against the deployment yet.

The full list of differences from the design, with the reason for each, is in
[deviations.md](docs/task2/deviations.md).

## Repository layout

```text
backend/        FastAPI application, migrations, seed and tests
  app/          domain, application, infrastructure and api layers
  alembic/      hand written migrations and the frozen baseline
  tests/        unit, component, api and integration tests
frontend/       React application
  src/          screens by role, shared components and the API client
  e2e/          browser and accessibility tests
infra/          setup, operations and the deployment scripts
docs/task1/     the submitted Task 1 design document and its images
docs/task2/     the Task 2 evidence, the presentation outline and the slides
.github/        workflows, issue forms, pull request template, Dependabot
```

[CHANGELOG.md](CHANGELOG.md) records what each release added.
