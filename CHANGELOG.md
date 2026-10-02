# Changelog

Every release of Toolshed Hire is listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Version `1.0.0` is reserved for the final release, when the built system matches
the whole design document.

## [Unreleased]

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

### Removed

- The demonstration role switcher and the on screen list of sample accounts.

### Changed

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
