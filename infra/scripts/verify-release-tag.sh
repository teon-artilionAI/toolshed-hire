#!/usr/bin/env bash
#
# Refuse to deploy a release tag that is malformed or does not sit on main.
#
# A tag can be pushed from any commit. Production must only ever run code that
# went through a release pull request into main, so this checks two things
# before anything else happens. The tag has the form vX.Y.Z, and the commit it
# points at is reachable from main.

set -euo pipefail

: "${RELEASE_TAG:?RELEASE_TAG is not set}"
: "${GITHUB_SHA:?GITHUB_SHA is not set}"

RELEASE_TAG_PATTERN='^v[0-9]+\.[0-9]+\.[0-9]+$'
MAIN_BRANCH="${MAIN_BRANCH:-main}"

if [[ ! "${RELEASE_TAG}" =~ ${RELEASE_TAG_PATTERN} ]]; then
  echo "::error title=Not a release tag::${RELEASE_TAG} does not have the form vX.Y.Z, so it does not deploy."
  exit 1
fi

git fetch --quiet origin "${MAIN_BRANCH}"

if ! git merge-base --is-ancestor "${GITHUB_SHA}" "origin/${MAIN_BRANCH}"; then
  echo "::error title=Tag is not on ${MAIN_BRANCH}::${RELEASE_TAG} points at ${GITHUB_SHA}, which is not reachable from ${MAIN_BRANCH}. Only a commit that was merged into ${MAIN_BRANCH} through a release may be deployed to production."
  exit 1
fi

echo "${RELEASE_TAG} is a release tag on ${MAIN_BRANCH} at ${GITHUB_SHA}."
