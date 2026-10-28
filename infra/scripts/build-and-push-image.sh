#!/usr/bin/env bash
#
# Build the API image, push it to Artifact Registry and report its digest.
#
# The digest is what everything downstream uses. A tag is mutable, so deploying
# by tag means the artifact that passed the smoke test and the artifact serving
# traffic are not provably the same bytes. The digest is the only identifier
# that makes that guarantee.
#
# Required environment:
#   REGION                        Artifact Registry location, for example europe-west2
#   PROJECT_ID                    Google Cloud project id
#   ARTIFACT_REGISTRY_REPOSITORY  Repository name inside that location
#   IMAGE_NAME                    Image name inside that repository
#   GITHUB_SHA                    Commit being built, used as the tag
#
# Optional environment:
#   GITHUB_OUTPUT   When set, image_digest is written to it
#   RELEASE_TAG     A release such as v1.0.0. When set, the image is also
#                   pushed under that tag, which the repository's cleanup
#                   policy keeps for good, so a rollback always has the
#                   previous release's image to go back to
#   GITHUB_SERVER_URL, GITHUB_REPOSITORY   Used for the source label only
#
# Prints the digest on stdout as its last line, so it is usable outside Actions.

set -euo pipefail

: "${REGION:?REGION is not set}"
: "${PROJECT_ID:?PROJECT_ID is not set}"
: "${ARTIFACT_REGISTRY_REPOSITORY:?ARTIFACT_REGISTRY_REPOSITORY is not set}"
: "${IMAGE_NAME:?IMAGE_NAME is not set}"
: "${GITHUB_SHA:?GITHUB_SHA is not set}"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_CONTEXT="${REPOSITORY_ROOT}/backend"

registry="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REGISTRY_REPOSITORY}"
repository="${registry}/${IMAGE_NAME}"
tag="${GITHUB_SHA}"

echo "Building ${repository}:${tag} from ${BACKEND_CONTEXT}"

docker build \
  --file "${BACKEND_CONTEXT}/Dockerfile" \
  --tag "${repository}:${tag}" \
  --label "org.opencontainers.image.revision=${GITHUB_SHA}" \
  --label "org.opencontainers.image.source=${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-unknown}" \
  "${BACKEND_CONTEXT}"

echo "Pushing ${repository}:${tag}"
docker push "${repository}:${tag}"

if [ -n "${RELEASE_TAG:-}" ]; then
  if ! [[ "${RELEASE_TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "::error title=Bad release tag::RELEASE_TAG is '${RELEASE_TAG}', which is not of the form vX.Y.Z, so it would not be kept by the cleanup policy."
    exit 1
  fi
  echo "Pushing ${repository}:${RELEASE_TAG} so the cleanup policy keeps this release"
  docker tag "${repository}:${tag}" "${repository}:${RELEASE_TAG}"
  docker push "${repository}:${RELEASE_TAG}"
fi

digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${repository}:${tag}")"
if [ -z "${digest}" ]; then
  echo "::error title=Digest not found::Pushed ${repository}:${tag} but docker inspect reported no RepoDigest for it, so the image cannot be deployed immutably. This normally means the push did not complete."
  exit 1
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "image_digest=${digest}" >> "${GITHUB_OUTPUT}"
fi

echo "${digest}"
