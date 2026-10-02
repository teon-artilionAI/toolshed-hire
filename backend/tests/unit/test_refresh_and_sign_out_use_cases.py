"""Refreshing and signing out, run against ports and nothing else (BR-48).

A refresh token works once. These tests pin what happens to the session it
names, to its successor and to its whole family when the token comes back a
second time, and they pin the two lifetimes with a clock the test moves.

The same behaviour is proved through HTTP and real SQL in
tests/api/test_refresh_and_logout.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import pytest

from app.application.identity.refresh_session import (
    REFRESH_REUSE_DETECTED_ACTION,
    SESSION_EXPIRED_MESSAGE,
    RefreshSessionCommand,
)
from app.application.identity.sign_out import SignOutCommand
from app.domain.account import Account
from app.domain.enums import RevokeReason
from app.domain.session import (
    REFRESH_ABSOLUTE_LIFETIME,
    REFRESH_IDLE_LIFETIME,
    hash_refresh_token,
)
from tests.support.identity_desk import Desk

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
SIX_DAYS: Final[timedelta] = timedelta(days=6)
UNKNOWN_TOKEN: Final[str] = "made-up-refresh-token-nobody-was-given"


@pytest.fixture
def desk() -> Desk:
    return Desk()


@pytest.fixture
def account(desk: Desk) -> Account:
    return desk.identity.add_account()


class TestRotation:
    """Every use of a token retires it and issues the next one."""

    def test_a_refresh_returns_a_new_pair_for_the_same_account(
        self, desk: Desk, account: Account
    ) -> None:
        first = desk.sign_in()
        second = desk.refresh(first.refresh_token)
        assert second.refresh_token != first.refresh_token
        assert second.account.id == account.id
        assert desk.tokens.issued_for == [account.id, account.id]

    def test_the_old_session_is_stamped_and_the_successor_joins_its_family(
        self, desk: Desk, account: Account
    ) -> None:
        first = desk.sign_in()
        desk.clock.advance(ONE_SECOND)
        second = desk.refresh(first.refresh_token)
        old, new = sorted(
            desk.identity.committed.sessions.values(), key=lambda session: session.issued_at
        )
        assert old.rotated_at == desk.clock.now()
        assert old.revoked_reason is RevokeReason.ROTATION
        assert new.family_id == old.family_id
        assert new.token_hash == hash_refresh_token(second.refresh_token)
        assert new.revoked_at is None
        assert new.expires_at == old.expires_at

    def test_the_successor_can_be_refreshed_in_turn(self, desk: Desk, account: Account) -> None:
        token = desk.sign_in().refresh_token
        for _ in range(3):
            token = desk.refresh(token).refresh_token
        assert desk.revoke_reasons() == [RevokeReason.ROTATION] * 3 + [None]


class TestReuse:
    """A token presented twice ends its whole family (BR-48)."""

    def test_the_second_use_is_refused_and_revokes_the_live_successor(
        self, desk: Desk, account: Account
    ) -> None:
        first = desk.sign_in()
        second = desk.refresh(first.refresh_token)
        desk.refresh_refused(first.refresh_token)
        assert desk.revoke_reasons() == [RevokeReason.ROTATION, RevokeReason.REUSE_DETECTED]
        desk.refresh_refused(second.refresh_token)

    def test_it_writes_the_reuse_event_against_the_account(
        self, desk: Desk, account: Account
    ) -> None:
        first = desk.sign_in()
        desk.refresh(first.refresh_token)
        desk.refresh_refused(first.refresh_token)
        (event,) = [
            event
            for event in desk.store.committed.audit_events
            if event.action == REFRESH_REUSE_DETECTED_ACTION
        ]
        (family_id,) = {session.family_id for session in desk.identity.committed.sessions.values()}
        assert event.entity_id == account.id
        assert event.actor_user_id is None
        assert event.after_state == {
            "session_family_id": str(family_id),
            "revoked_session_count": 1,
            "reason": "REUSE_DETECTED",
        }

    def test_another_family_of_the_same_account_is_left_alone(
        self, desk: Desk, account: Account
    ) -> None:
        phone = desk.sign_in()
        laptop = desk.sign_in()
        desk.refresh(phone.refresh_token)
        desk.refresh_refused(phone.refresh_token)
        assert desk.refresh(laptop.refresh_token).account.id == account.id


class TestARefusedRefresh:
    """Every refusal says the same thing."""

    @pytest.mark.parametrize("token", [None, "", UNKNOWN_TOKEN])
    def test_no_token_and_an_unknown_token_are_refused(self, desk: Desk, token: str | None) -> None:
        refusal = desk.refresh_refused(token)
        assert refusal.message == SESSION_EXPIRED_MESSAGE
        assert refusal.code == "session-expired"
        assert refusal.detail == {}

    def test_a_session_idle_for_seven_days_is_refused(self, desk: Desk, account: Account) -> None:
        token = desk.sign_in().refresh_token
        desk.clock.advance(REFRESH_IDLE_LIFETIME - ONE_SECOND)
        token = desk.refresh(token).refresh_token
        desk.clock.advance(REFRESH_IDLE_LIFETIME)
        desk.refresh_refused(token)

    def test_a_busy_session_is_refused_fourteen_days_after_the_sign_in(
        self, desk: Desk, account: Account
    ) -> None:
        token = desk.sign_in().refresh_token
        for _ in range(2):
            desk.clock.advance(SIX_DAYS)
            token = desk.refresh(token).refresh_token
        desk.clock.advance(REFRESH_ABSOLUTE_LIFETIME - 2 * SIX_DAYS - ONE_SECOND)
        token = desk.refresh(token).refresh_token
        desk.clock.advance(ONE_SECOND)
        desk.refresh_refused(token)

    def test_the_cookie_lifetime_shrinks_to_what_the_family_has_left(
        self, desk: Desk, account: Account
    ) -> None:
        grant = desk.sign_in()
        assert grant.refresh_max_age_seconds == int(REFRESH_IDLE_LIFETIME.total_seconds())
        for _ in range(2):
            desk.clock.advance(SIX_DAYS)
            grant = desk.refresh(grant.refresh_token)
        assert grant.refresh_max_age_seconds == int(timedelta(days=2).total_seconds())

    def test_an_account_deactivated_since_the_sign_in_is_refused(
        self, desk: Desk, account: Account
    ) -> None:
        token = desk.sign_in().refresh_token
        desk.identity.account(account.id).is_active = False
        desk.refresh_refused(token)
        assert desk.revoke_reasons() == [None]

    def test_an_expired_token_is_not_treated_as_reuse(self, desk: Desk, account: Account) -> None:
        token = desk.sign_in().refresh_token
        desk.clock.advance(REFRESH_IDLE_LIFETIME)
        desk.refresh_refused(token)
        assert REFRESH_REUSE_DETECTED_ACTION not in {
            event.action for event in desk.store.committed.audit_events
        }

    def test_the_token_is_left_out_of_the_representation_of_the_command(self) -> None:
        assert UNKNOWN_TOKEN not in repr(RefreshSessionCommand(presented_token=UNKNOWN_TOKEN))


class TestSigningOut:
    """The family is revoked on the server, and nothing is ever refused."""

    def test_it_revokes_the_session_with_the_reason_logout(
        self, desk: Desk, account: Account
    ) -> None:
        token = desk.sign_in().refresh_token
        assert desk.sign_out(token) == 1
        assert desk.revoke_reasons() == [RevokeReason.LOGOUT]
        desk.refresh_refused(token)

    def test_it_revokes_the_live_session_when_handed_an_older_token_of_the_family(
        self, desk: Desk, account: Account
    ) -> None:
        first = desk.sign_in()
        second = desk.refresh(first.refresh_token)
        assert desk.sign_out(first.refresh_token) == 1
        assert desk.revoke_reasons() == [RevokeReason.ROTATION, RevokeReason.LOGOUT]
        desk.refresh_refused(second.refresh_token)

    @pytest.mark.parametrize("token", [None, "", UNKNOWN_TOKEN])
    def test_no_token_and_an_unknown_token_change_nothing(
        self, desk: Desk, account: Account, token: str | None
    ) -> None:
        live = desk.sign_in()
        assert desk.sign_out(token) == 0
        assert desk.refresh(live.refresh_token).account.id == account.id

    def test_signing_out_twice_is_harmless(self, desk: Desk, account: Account) -> None:
        token = desk.sign_in().refresh_token
        desk.sign_out(token)
        assert desk.sign_out(token) == 0

    def test_the_token_is_left_out_of_the_representation_of_the_command(self) -> None:
        assert UNKNOWN_TOKEN not in repr(SignOutCommand(presented_token=UNKNOWN_TOKEN))
