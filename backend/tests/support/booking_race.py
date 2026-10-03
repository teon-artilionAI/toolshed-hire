"""Plumbing for tests that send many requests to the real application at once.

`application_on` gives the real application a session of its own for every
request, opened on the engine the test hands in. The integration suite uses a
NullPool engine, so every request then holds a PostgreSQL connection of its
own and twenty requests are twenty transactions that genuinely overlap. The
application's own pool is five connections wide and would let five in at a
time, which is a gentler race than the one worth proving.

`post_at_once` sends one request from each of a set of threads. A barrier
holds every thread until all of them have arrived, so no request can finish
before the last one has started. `post_bodies_at_once` does the same for
requests that carry a JSON body, such as two checkouts of one reservation.

Nothing here shares a session between threads. A token is minted on the main
thread and handed to the thread that uses it, and each thread drives a test
client of its own.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine
from sqlmodel import Session

from app.api.deps import get_clock, get_notification_gateway
from app.infrastructure.database import get_session
from app.infrastructure.notification import FakeEmailGateway
from app.main import app as production_app
from tests.support.clock import FixedClock

logger = logging.getLogger(__name__)

# Long enough for twenty local transactions, short enough that a deadlock
# fails the suite in seconds and does not hang it.
BARRIER_TIMEOUT_SECONDS: Final[float] = 30.0
RESULT_TIMEOUT_SECONDS: Final[float] = 60.0


@contextmanager
def application_on(
    engine: Engine, clock: FixedClock, gateway: FakeEmailGateway | None = None
) -> Iterator[FastAPI]:
    """Yield the real application, with a session of its own for every request.

    Args:
        engine: The engine each request opens its session on.
        clock: The clock the application is given.
        gateway: The email gateway. A fake that accepts everything when omitted.

    """
    chosen_gateway = gateway or FakeEmailGateway()

    def _session() -> Iterator[Session]:
        """Open a session for one request and close it when the request ends."""
        with Session(engine) as session:
            yield session

    overrides = {
        get_session: _session,
        get_clock: lambda: clock,
        get_notification_gateway: lambda: chosen_gateway,
    }
    production_app.dependency_overrides.update(overrides)
    try:
        yield production_app
    finally:
        for dependency in overrides:
            production_app.dependency_overrides.pop(dependency, None)


def post_at_once(
    application: FastAPI, requests: Sequence[tuple[str, dict[str, str]]]
) -> list[Response]:
    """Post every request from a thread of its own, all released at the same moment.

    Args:
        application: The application to post to.
        requests: The path and the headers of each request.

    Returns:
        The responses, in the order the requests were given.

    Raises:
        TimeoutError: If a request has not finished within the result timeout,
            which means the requests deadlocked in a way PostgreSQL did not
            resolve and the test must not hang waiting for.

    """
    return post_bodies_at_once(application, [(path, headers, None) for path, headers in requests])


def post_bodies_at_once(
    application: FastAPI,
    requests: Sequence[tuple[str, dict[str, str], dict[str, object] | None]],
) -> list[Response]:
    """Post every request with its JSON body from a thread of its own, released together.

    Args:
        application: The application to post to.
        requests: The path, the headers and the body of each request. A
            request with no body is posted with none.

    Returns:
        The responses, in the order the requests were given.

    Raises:
        TimeoutError: If a request has not finished within the result timeout.

    """
    barrier = threading.Barrier(len(requests))

    def _post(path: str, headers: dict[str, str], body: dict[str, object] | None) -> Response:
        """Wait for every other thread, then post one request."""
        client = TestClient(application)
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        if body is None:
            return client.post(path, headers=headers)
        return client.post(path, headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        futures = [pool.submit(_post, path, headers, body) for path, headers, body in requests]
        responses = [future.result(timeout=RESULT_TIMEOUT_SECONDS) for future in futures]
    logger.info(
        "test.requests_posted_at_once",
        extra={
            "request_count": len(requests),
            "statuses": sorted(response.status_code for response in responses),
        },
    )
    return responses


__all__ = ["application_on", "post_at_once", "post_bodies_at_once"]
