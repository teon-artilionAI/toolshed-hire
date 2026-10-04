# Changelog

Every release of Toolshed Hire is listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Version `1.0.0` is reserved for the final release, when the built system matches
the whole design document.

## [Unreleased]

## [0.4.1] - 2026-10-04

Fixes found by walking the 0.4.0 release by hand in a browser, as a customer,
a counter assistant and the owner. None of them lost data. Each one told a
person something wrong or made the first visit slower than it had to be.

### Fixed

- The browser waits fifteen seconds for an answer instead of eight, so the
  first visit after a quiet spell no longer gives up on every read while the
  API and the database wake. The API also starts with start up CPU boost.
- The home page names the three branches instead of the suburbs they stand in.
- A booking that has been collected or is back points to the hire history for
  its charges, and says why there is nothing to cancel, instead of saying
  nothing was charged and to ring the branch.
- The seeded accounts are opened on 5 January 2026, before their hire
  history. A database seeded earlier is put right on the next run.
- The deposit card of a return shows no settlement figures while a damage
  report is still to be filed, and says when a correction gave money back
  after the hire was settled.
- A unit on a return no longer lists a reversed or waived late fee as charged.
- The diary says when a booking is due back, instead of a date that read like
  the day it came back.
- A failed journey on staging keeps its screenshots.

### Security

- wheel 0.46.3 in the backend build requirements, for GHSA-8rrh-rw8j-w5fx. The
  advisory is in `wheel unpack`, which the build never runs, but the pinned
  0.45.1 was in the affected range.

## [0.4.0] - 2026-10-04

The Admin console and the release checks. The owner can see which equipment
earns its keep, read the audit trail, correct a charge without editing
history, and maintain the catalogue, the asset register and the staff
accounts. This is the release Task 2 is assessed on.

### Added

- A utilisation and gross contribution report per unit, model, category and
  branch for any period, with both definitions shown in full, a streamed CSV
  export and a hand worked dataset that every grouping is tested against.
- An admin dashboard of the whole business today across the three branches.
- The audit trail, filtered by record, action, person and dates, and the
  notification log, where a failed confirmation can be sent again.
- Charge corrections for the owner. A pending charge can be waived, a settled
  one reversed with a new charge that points at it, and a hire adjusted, each
  with a written reason. A settled hire only takes a correction that gives
  money back.
- Releasing a unit from a booking with a reason, and finding a replacement
  unit for a booking that is short.
- Catalogue and pricing management. A price change never touches a booking
  that already exists.
- The asset register, with registration, editing and moves through the
  documented lifecycle. A unit with a booking cannot be retired, and a retired
  unit keeps its history.
- Staff accounts, roles and branch assignment, deactivation that signs a person
  out everywhere, and customer holds. The last admin can never be removed.
- A season of trading history in the seed, June to September 2026, so the
  report has something to report.
- The customer, counter and admin journeys run in a browser against staging
  after every staging deployment.
- A check of the security headers and the TLS floor of the deployed site after
  every deployment.

### Changed

- The screens promise an email only when this environment can deliver it,
  because the session now says whether the address can be reached.
- A customer on hold is refused a booking with the same neutral message,
  whatever put the account on hold.
- Completing a password reset also verifies the email address.
- Old throttle counters are pruned by the lazy sweep in one bounded statement
  instead of by an unbounded delete on the sign in path.
- TypeScript strict mode is stated in every config, and the linter refuses an
  explicit any.
- setuptools 84.0.0, postcss 8.5.28, and react-dom with its types 19.3.0.

### Fixed

- The asset register no longer offers to put a unit back into service while
  one of its damage reports is still open.
- A query plan test that passed or failed depending on the planner's choice
  on a nearly empty table now proves what matters, that the read never walks
  the whole table.

## [0.3.0] - 2026-10-03

Registration and the counter journey. A new customer can open an account, and
a counter assistant can find or register a customer, book for them, hand the
equipment over, take it back late or damaged and settle the deposit. The
worked example in the design document gives its documented figures.

### Added

- Registration with an email verification link, a password reset link and
  profile editing. The API answers the same way whether or not an address has
  an account, the tokens are single use, stored only as hashes and time
  limited, and a completed reset signs every device out.
- A privacy notice, linked from every screen and from the registration form.
- Customer lookup by name, phone or email and walk in registration with no
  login at the counter, with a trigram index over the digits of a phone number.
- Counter bookings through the same create, hold and confirm path as an online
  booking, held to the assistant's own branch.
- Checkout, which creates the rental, its items and the hire and deposit
  charges and puts each unit on hire in one transaction. A repeated checkout
  returns the existing rental.
- The counter dashboard, the branch diary by day or week and the asset locator
  across every branch, each a query with a fixed number of statements.
- No shows. The lazy sweep turns a confirmed booking that was never collected
  into a no show once its branch has closed, and three no shows in twelve
  months put the customer on hold. Staff can also mark one by hand.
- The late fee policy, the second Strategy, which charges each whole day past
  due per unit and stops at fourteen days. Late fees are VAT inclusive.
- Returns item by item, deposit settlement with the remainder released, a
  simulated balance payment, recording a unit as lost, and an overdue list.
- Damage reports with an explicit chargeable decision, quarantine at return,
  recovery capped at the replacement value, and resolution or write off by
  the owner.
- A customer's hire history with charges and deposit position.

### Changed

- An account is locked after five failed sign ins inside fifteen minutes,
  rather than five in a row.
- A reservation cancelled without ever holding a unit no longer shows in the
  customer's list.
- A booking can no longer start today once its branch has closed for the day.
- The dependency audit fails on any high or critical advisory that has no
  reviewed exception still in date, instead of on every advisory alike. The
  one exception today is a build time advisory in Tailwind CSS 3.
- A test fails the build when the committed API description no longer matches
  the code.

### Fixed

- My Reservations and My Account no longer run off the side of a phone screen.
- The Today item in the counter menu no longer shows as the current page on
  every counter screen.

## [0.2.0] - 2026-10-02

The customer journey. A visitor can browse the catalogue and check availability
across the three branches, and a signed in customer can price, hold, confirm
and cancel a reservation.

### Added

- An audit event for every state change, written in the same transaction as the
  change. If the audit event cannot be written, the change is not made.
- An email gateway with a Resend adapter and a transactional outbox. A booking
  is never lost or rolled back because an email could not be sent.
- A public catalogue with categories, models and prices, and an availability
  search that says for a date range at which branches a model is free. The
  catalogue home, search results and model detail screens now read from it.
- A frontend data layer with a typed API client, cached server state, shared
  loading, error and empty states and an error boundary. The wire types are
  generated from the API's OpenAPI document.
- Browser tests that run against the real API and a seeded database.
- Sessions. Sign in returns a short lived access token and sets an HttpOnly
  refresh cookie that is rotated on every use. Presenting a refresh token that
  has already been used revokes the whole session family. Sign out revokes on
  the server.
- Account lockout after five failed sign ins, and throttling per email and per
  client address.
- A declared access policy on every route. The application refuses to start if
  a route has none.
- A real session in the frontend. The access token is held in memory only, a
  reload restores the session through the refresh cookie, and screens are
  guarded by role.
- A notice on every screen that is not connected to the API yet, saying that it
  still shows sample data.
- Reservations. A customer builds a basket, sees the server's figures, holds
  named units for thirty minutes, confirms, and can cancel. Every change of
  status goes through one set of state rules, an expired hold releases its
  units, and a confirmation email is queued when the booking is confirmed.
- A pricing policy and a quote. A hire is charged by whole weeks plus the
  remaining days, or by the day, whichever is lower, with VAT on top and the
  deposit shown separately. The price is calculated in one place.

### Removed

- `POST /api/allocations`, the walking skeleton's single route for holding one
  line. The reservation routes replace it.
- The demonstration role switcher and the on screen list of sample accounts.

### Changed

- Refusal messages from the catalogue, availability and quote routes are plain
  sentences. The rule identifier and the rejected values go to the log.
- Sign in moved from `POST /api/auth/sign-in` to `POST /api/auth/login`, the
  path the design document names.
- The use cases now depend on ports. Repositories, the unit of work, the clock
  and the email adapter implement them in the infrastructure layer, and an
  import contract stops the application layer from importing infrastructure.

## [0.1.0] - 2026-10-02

The first release that is deployed. It carries no new feature for a customer or
a counter assistant yet. It puts the foundations in place, which are the branch
model and checks, the documented database schema, a seeded fleet, and a pipeline
that takes a merge to staging and a release tag to production.

### Added

- Branching workflow, pull request template and issue forms.
- Fast checks on every push and integration checks on every pull request, with
  a layer import contract, a secret scan, a coverage floor, dependency audits,
  and browser and accessibility tests.
- First unit, component and browser tests for the frontend.
- A local PostgreSQL service for development and integration tests.
- A seed that loads three branches, 120 product models, 400 tagged assets,
  demonstration accounts and the worked example from the design document. It is
  safe to run more than once.
- A restricted database role for the running application. It can select and
  insert on the audit table and nothing else, so the audit trail cannot be
  rewritten by the application that writes it.
- Reference sequences for rentals and damage reports.
- Automatic deployment to a staging environment on every merge into `develop`,
  and deployment to production from a `vX.Y.Z` tag on `main` through a candidate
  revision that is smoke tested before it takes traffic.
- A request id on every request, returned in `X-Request-ID`, written to every
  log line and included in every error response.
- One structured access log line per request, with secrets redacted from all
  log output.
- Security headers on the API and the frontend, including a Content Security
  Policy.
- The deployed revision in the health response.

### Changed

- The container base image is pinned by digest.
- The interactive API documentation is served only in development and test.
- A deployment with missing configuration now fails instead of skipping.
- The two original test workflows are replaced by `ci-fast.yml` and
  `ci-integration.yml`.
- The database schema is now the documented baseline of seventeen tables with
  singular names. The first migration was rewritten in place, because no
  database outside CI and local containers had run it. A local database that
  ran the old one has to be recreated with `docker compose down -v`.

## Baseline, 16 August 2026

The state submitted for Task 1. It holds the clickable prototype of all 24
screens driven by fixture data, and a walking skeleton of the API that proves
the allocation path against PostgreSQL.
