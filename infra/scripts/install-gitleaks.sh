#!/usr/bin/env bash
# Install the gitleaks version the artifact scan is pinned to.
#
# The project already uses gitleaks for the repository history scan. The
# artifact scan needs the same tool over a directory. The release asset is
# pinned by version and SHA-256 so a changed download cannot run silently.
set -euo pipefail

VERSION="8.30.1"
SHA256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
ARCHIVE="gitleaks_${VERSION}_linux_x64.tar.gz"
URL="https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/${ARCHIVE}"
DEST="${RUNNER_TEMP:-/tmp}/gitleaks-${VERSION}"

if [[ -x "${DEST}/gitleaks" ]]; then
  echo "gitleaks ${VERSION} is already installed at ${DEST}."
else
  TEMP_DIR="$(mktemp -d)"
  trap 'rm -rf "${TEMP_DIR}"' EXIT
  curl --fail --silent --show-error --location "${URL}" --output "${TEMP_DIR}/${ARCHIVE}"
  printf '%s  %s\n' "${SHA256}" "${TEMP_DIR}/${ARCHIVE}" | sha256sum --check --status
  mkdir -p "${DEST}"
  tar --extract --gzip --file "${TEMP_DIR}/${ARCHIVE}" --directory "${DEST}" gitleaks
  echo "Installed gitleaks ${VERSION} at ${DEST}."
fi

"${DEST}/gitleaks" version
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "${DEST}" >> "${GITHUB_PATH}"
else
  export PATH="${DEST}:${PATH}"
fi