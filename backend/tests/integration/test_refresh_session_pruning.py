"""Pruning expired refresh sessions on PostgreSQL, as the operator role (#90).

Sessions are written on either side of the cutoff, ninety days after their
expiry. The pruning deletes exactly those past it, a batch at a time, and
leaves every other one, live, revoked or recently expired, where it was.

The operator role is the owner of the tables here, as `toolshed_migrate` is
where the job is deployed. The application role still holds no DELETE on
`refresh_session`, which the catalogue says and a DELETE it tries proves.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Final

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, col, select

from app.application.identity.session_pruning import (
    expired_session_cutoff,
    prune_expired_sessions,
)
from app.infrastructure.models import RefreshSession
from app.infrastructure.session_pruning import SqlExpiredSessionStore
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    INSUFFICIENT_PRIVILEGE_SQLSTATE,
    engine_as,
    provision_restricted_roles,
    sqlstate_of_refusal,
)

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

NOW = FixedClock().now()
CUTOFF = expired_session_cutoff(NOW)
SMALL_BATCH: Final[int] = 3
PAST_THE_CUTOFF: Final[int] = 7
INSERT_SESSIONS = text(
    "INSERT INTO refresh_session "
    "(id, user_account_id, family_id, token_hash, issued_at, expires_at) "
    "SELECT gen_random_uuid(), :account, gen_random_uuid(), "
    "md5(:tag || n::text) || md5(n::text || :tag), "
    "CAST(:expires AS timestamptz) - interval '14 days' - n * interval '1 minute', "
    "CAST(:expires AS timestamptz) - n * interval '1 minute' "
    "FROM generate_series(1, :count) AS n"
)


@pytest.fixture(scope="module")
def application_engine(postgres_engine: Engine, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the restricted application role."""
    provision_restricted_roles(postgres_engine, postgres_url)
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


def add_sessions(
    engine: Engine, account: object, *, expiring_before: datetime, count: int, tag: str
) -> None:
    """Commit `count` sessions a minute apart, the latest expiring a minute before the instant."""
    with engine.begin() as connection:
        connection.execute(
            INSERT_SESSIONS,
            {"account": account, "expires": expiring_before, "count": count, "tag": tag},
        )


def expiries(engine: Engine) -> list[datetime]:
    """Return the expiry of every session left, oldest first."""
    with Session(engine) as session:
        statement = select(RefreshSession.expires_at).order_by(col(RefreshSession.expires_at))
        return list(session.exec(statement).all())


@pytest.fixture
def account(postgres_session: Session, postgres_factory: Factory) -> object:
    """Commit an account for the sessions to belong to."""
    built = postgres_factory.user()
    postgres_session.commit()
    return built.id


class TestThePruning:
    """Exactly the sessions past the cutoff, a batch at a time."""

    def test_only_the_sessions_past_the_cutoff_are_deleted(
        self, postgres_engine: Engine, account: object
    ) -> None:
        add_sessions(
            postgres_engine, account, expiring_before=CUTOFF, count=PAST_THE_CUTOFF, tag="old"
        )
        add_sessions(
            postgres_engine,
            account,
            expiring_before=CUTOFF + timedelta(days=1),
            count=4,
            tag="recent",
        )
        add_sessions(
            postgres_engine, account, expiring_before=NOW + timedelta(days=7), count=2, tag="live"
        )
        deleted = prune_expired_sessions(
            SqlExpiredSessionStore(postgres_engine), NOW, batch_size=SMALL_BATCH
        )
        assert deleted == PAST_THE_CUTOFF
        left = expiries(postgres_engine)
        assert len(left) == 6
        assert min(left) >= CUTOFF

    def test_nothing_past_the_cutoff_deletes_nothing(
        self, postgres_engine: Engine, account: object
    ) -> None:
        add_sessions(postgres_engine, account, expiring_before=NOW, count=3, tag="young")
        store = SqlExpiredSessionStore(postgres_engine)
        assert prune_expired_sessions(store, NOW, batch_size=SMALL_BATCH) == 0
        assert len(expiries(postgres_engine)) == 3


class TestTheApplicationRoleStillCannotDelete:
    """The delete belongs to the operator alone."""

    def test_the_catalogue_says_the_application_role_has_no_delete(
        self, postgres_engine: Engine, application_engine: Engine
    ) -> None:
        with postgres_engine.connect() as connection:
            allowed = connection.execute(
                text("SELECT has_table_privilege(:role, 'refresh_session', 'DELETE')"),
                {"role": APPLICATION_ROLE},
            ).scalar_one()
        assert allowed is False

    def test_a_delete_as_the_application_role_is_refused(
        self, postgres_engine: Engine, application_engine: Engine, account: object
    ) -> None:
        add_sessions(postgres_engine, account, expiring_before=CUTOFF, count=2, tag="old")
        with pytest.raises(DBAPIError) as refused:
            prune_expired_sessions(
                SqlExpiredSessionStore(application_engine), NOW, batch_size=SMALL_BATCH
            )
        assert sqlstate_of_refusal(refused.value) == INSUFFICIENT_PRIVILEGE_SQLSTATE
        assert len(expiries(postgres_engine)) == 2
