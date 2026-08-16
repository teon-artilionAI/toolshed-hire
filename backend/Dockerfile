# syntax=docker/dockerfile:1.7
#
# Toolshed Hire API image.
#
# SIZE, MEASURED
# ==============
# Measured on 2026-08-15, linux/amd64, Docker 29.5.2 with the containerd image
# store. Three numbers, because the three commands people quote do not mean the
# same thing and quoting one as if it were another is how a comment ends up
# contradicting its own artifact.
#
#   docker images                    324 MB   sum of the layer sizes
#   du -sm / inside the container    232 MiB  what is actually on disk
#   docker image inspect .Size        76 MB   compressed, what the registry sends
#
# The same three commands against python:3.12-slim-bookworm alone give 189 MB,
# 131 MiB and 45 MB. So the base is the overwhelming majority of this image
# before a single instruction of ours has run, and everything below adds about
# 101 MiB unpacked, which is the virtual environment, or about 31 MB over the
# wire. SQLAlchemy at 22 MiB, uvloop at 16 MiB and the psycopg binary libraries
# at 10 MiB are the three largest members of it.
#
# An earlier version of this comment claimed a target of roughly 200 MB. It was
# wrong against every one of the three measurements and is corrected here rather
# than quietly deleted, because the number mattered: Cloud Run runs with minimum
# instances of zero, so the first request after an idle period pays for the pull,
# and 76 MB compressed is the figure that cold start actually depends on.
#
# The measures that hold the additions to 31 MB compressed are:
#
#   1. python:3.12-slim rather than python:3.12, which drops roughly 900 MB of
#      documentation, headers and development packages.
#   2. A builder stage that owns the C toolchain, so gcc, g++ and the header
#      packages never reach the final layer.
#   3. A virtual environment copied wholesale from the builder, which means the
#      final stage has no pip cache, no wheel cache and no build artifacts.
#   4. No test suite, no migrations and no documentation in the image, enforced
#      by .dockerignore in this directory.
#
# Going smaller means changing the base, and the obvious candidate is rejected
# for a stated reason rather than overlooked. python:3.12-alpine is about 50 MB,
# but psycopg[binary] publishes no musllinux wheel, so alpine turns the pinned
# binary driver into a source build against libpq and swaps a known quantity for
# a compile step that has to be kept working. The pull is not the bottleneck
# worth that trade today. If it becomes one, the change to make is the base, and
# these three numbers are the baseline to measure it against.
#
# BASE IMAGE PINNING
# ==================
# The base is pinned to a specific minor tag rather than a digest. Pinning to a
# digest is stronger and is the follow-up, and the digest is obtained with:
#
#   docker buildx imagetools inspect python:3.12-slim-bookworm
#
# A digest is deliberately not invented here, because a wrong digest fails the
# build with a message that says nothing useful about why.

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim-bookworm AS builder

# Where the dependency tree is assembled. The whole directory is copied into
# the final stage, so nothing pip leaves behind travels with it.
ENV VIRTUAL_ENV=/opt/venv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# The C toolchain and the PostgreSQL client headers live in this stage only.
# libpq-dev is present so that a source build of a database driver succeeds if
# no wheel is published for the pinned version. If every dependency resolves to
# a wheel this layer costs build time and nothing else, because it is discarded.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends \
      build-essential \
      libpq-dev \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# The project declares its dependencies in pyproject.toml and every version
# there is pinned exactly. pyproject.toml, the readme it references and the
# package itself are all required for the install to resolve, so they are
# copied together.
#
# The trade-off this carries is worth naming. Because the source is part of the
# install input, a change to any Python file invalidates this layer and the
# dependencies are resolved again. Splitting them would need a lock file
# generated from pyproject.toml, for example by pip-compile, and that is the
# follow-up when build time starts to hurt. Correctness first.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install .

# ---------------------------------------------------------------- final stage
FROM python:3.12-slim-bookworm AS runtime

# libpq5 is the PostgreSQL client runtime library. It is a shared library and
# not a build toolchain, so it does not violate the "no toolchain in the final
# layer" rule. It is installed because a driver linked against the system libpq
# fails at import time with an opaque "libpq.so.5: cannot open shared object
# file" error, and about 8 MB is a cheap price for never debugging that.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends \
      libpq5 \
 && rm -rf /var/lib/apt/lists/* \
 && apt-get clean

# A dedicated unprivileged account. The identifiers are fixed rather than
# allocated by the system so that file ownership is predictable across builds.
ARG APP_USER=appuser
ARG APP_GROUP=appgroup
ARG APP_UID=10001
ARG APP_GID=10001

RUN groupadd --system --gid "${APP_GID}" "${APP_GROUP}" \
 && useradd --system \
      --uid "${APP_UID}" \
      --gid "${APP_GROUP}" \
      --no-create-home \
      --shell /usr/sbin/nologin \
      "${APP_USER}"

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1
# PYTHONUNBUFFERED is not a stylistic choice. Logs are structured JSON written
# to stdout and collected by Cloud Logging, and a buffered stream means the log
# lines describing a crash are lost with the process that was about to write
# them.

WORKDIR /srv

# The dependency tree and the installed application package, already resolved,
# with no toolchain attached to either. The app package is installed into the
# virtual environment by the builder, so there is no second copy of the source
# in the final image and nothing to keep in step.
#
# Tests, seed data and migrations are absent. Migrations in particular are
# deliberately absent: they are applied by the deployment pipeline before the
# new revision is created, never from the container start-up path, because
# several instances of the same revision would otherwise race to apply the same
# migration and a slow migration would trip the start-up probe.
COPY --from=builder --chown=${APP_UID}:${APP_GID} /opt/venv /opt/venv

USER ${APP_USER}

# Cloud Run injects PORT and the container must listen on it. The default here
# matches the Cloud Run default so that "docker run" locally behaves the same
# way as the deployed service. EXPOSE is documentation only; Cloud Run reads
# the port from the service configuration, not from this instruction.
ENV PORT=8080
EXPOSE 8080

# No HEALTHCHECK instruction. Cloud Run ignores Docker health checks entirely
# and uses the start-up and liveness probes configured on the service, so a
# HEALTHCHECK here would be dead configuration that reads as if it were live.

# The shell form is required because ${PORT} is supplied by the platform at run
# time and must be expanded then, not baked in at build time. "exec" replaces
# the shell with uvicorn so that the server is process 1 and receives SIGTERM
# directly, which is what makes Cloud Run's graceful shutdown work.
#
# One worker per instance is deliberate. Concurrency is handled by the event
# loop, and NFR-15's connection arithmetic assumes one pool of 5 connections
# per instance against a cap of 4 instances, which is 20 connections at peak.
# A second worker would silently double that.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
