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

### Changed

- The two original test workflows are replaced by `ci-fast.yml` and
  `ci-integration.yml`.

## Baseline, 16 August 2026

The state submitted for Task 1. It holds the clickable prototype of all 24
screens driven by fixture data, and a walking skeleton of the API that proves
the allocation path against PostgreSQL.
