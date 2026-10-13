#!/bin/sh
# Compile the backend's two lockfiles from pyproject.toml, with a hash for
# every file pip may install.
#
#   requirements.txt      what the image installs (the running application)
#   requirements-dev.txt  what CI and a developer install (adds the dev extra)
#
# Run it from backend/ through Docker, never straight on a laptop:
#
#   docker run --rm -v "$PWD:/src" -w /src python:3.12-slim-bookworm@sha256:<digest> \
#     sh scripts/compile-lockfiles.sh
#
# The resolver answers for the platform it runs on. uvicorn[standard] pulls in
# uvloop only off Windows, for example, so a lock compiled on Windows would be
# missing a package the image needs. Running in the same base image as the
# Dockerfile, at the digest the Dockerfile pins, gives the answer the image and
# the Linux CI runners will see. CI runs this script the same way and fails when
# the result differs from what is committed (the lockfiles job in ci-fast.yml).
#
# --allow-unsafe keeps setuptools and wheel in the lock, and --build-deps-for
# adds the build backend from [build-system], so the project itself can be
# installed with --no-build-isolation and nothing is fetched without a hash.
set -eu

PIP_TOOLS_VERSION="7.6.1"

pip install --quiet --root-user-action=ignore --disable-pip-version-check \
    "pip-tools==${PIP_TOOLS_VERSION}"

# The header names this script, so a reader of the lock knows how to remake it.
export CUSTOM_COMPILE_COMMAND="sh scripts/compile-lockfiles.sh (through Docker, see the script)"

pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras \
    --build-deps-for wheel \
    --output-file requirements.txt pyproject.toml

pip-compile --quiet --generate-hashes --allow-unsafe --strip-extras \
    --extra dev --build-deps-for editable \
    --output-file requirements-dev.txt pyproject.toml

echo "lockfiles compiled with pip-tools ${PIP_TOOLS_VERSION}"
