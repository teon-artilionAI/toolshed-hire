# Changelog

Every release of Toolshed Hire is listed here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Version `1.0.0` is reserved for the final release, when the built system matches
the whole design document.

## [Unreleased]

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

### Changed

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
