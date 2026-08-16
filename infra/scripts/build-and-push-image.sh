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
#   REGION                        Artifact Registry location, for example europe-west1
#   PROJECT_ID                    Google Cloud project id
#   ARTIFACT_REGISTRY_REPOSITORY  Repository name inside that location
#   IMAGE_NAME                    Image name inside that repository
#   GITHUB_SHA                    Commit being built, used as the tag
#
# Optional environment:
#   GITHUB_OUTPUT   When set, image_digest is written to it
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

digest="$(docker inspect --format='{{index .RepoDigests 0}}' "${repository}:${tag}")"
if [ -z "${digest}" ]; then
  echo "::error title=Digest not found::Pushed ${repository}:${tag} but docker inspect reported no RepoDigest for it, so the image cannot be deployed immutably. This normally means the push did not complete."
  exit 1
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "image_digest=${digest}" >> "${GITHUB_OUTPUT}"
fi

echo "${digest}"
