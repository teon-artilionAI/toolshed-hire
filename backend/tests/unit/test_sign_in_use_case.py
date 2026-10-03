"""The sign in use case, run against ports and nothing else (BR-45, BR-46).

There is no database here, no HTTP and no bcrypt. The use case is handed an in
memory unit of work, a clock that stands still and a password verifier that
counts its calls. What these tests pin is what a good sign in leaves behind,
that the four refusals are one refusal from outside, and that every path
verifies exactly once.

The lockout and the two throttles are in test_sign_in_lockout_and_throttle.py.
The same behaviour is proved through HTTP and real SQL in tests/api/test_login.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.identity.sign_in import (
    INVALID_CREDENTIALS_MESSAGE,
    LOGIN_FAILED_ACTION,
    LOGIN_SUCCEEDED_ACTION,
    UNKNOWN_ACCOUNT_ID,
    SignInCommand,
)
from app.domain.account import LOCKOUT_DURATION, Account
from app.domain.enums import UserRole
from app.domain.identity import Branch
from app.domain.session import hash_refresh_token
from tests.support.factories import CLOSES_AT
from tests.support.identity_desk import CLIENT, UNKNOWN_EMAIL, WRONG_PASSWORD, Desk
from tests.support.memory_identity import KNOWN_EMAIL, KNOWN_PASSWORD, fake_hash


@pytest.fixture
def desk() -> Desk:
    return Desk()


@pytest.fixture
def account(desk: Desk) -> Account:
    return desk.identity.add_account()


class TestASuccessfulSignIn:
    """A session is opened, both tokens are issued and the count is cleared."""

    def test_it_returns_both_tokens_and_the_account(self, desk: Desk, account: Account) -> None:
        grant = desk.sign_in()
        assert grant.access_token.startswith("made-up-access-token")
        assert grant.account.id == account.id
        assert grant.account.email == KNOWN_EMAIL
        assert grant.account.role is UserRole.CUSTOMER
        assert grant.account.branch_code is None
        assert grant.account.email_verified is False

    def test_only_the_hash_of_the_refresh_token_is_stored(
        self, desk: Desk, account: Account
    ) -> None:
        grant = desk.sign_in()
        (session,) = desk.identity.committed.sessions.values()
        assert session.token_hash == hash_refresh_token(grant.refresh_token)
        assert grant.refresh_token not in repr(desk.identity.committed)
        assert session.user_account_id == account.id
        assert session.ip_address == CLIENT.address

    def test_neither_token_appears_in_the_representation_of_the_grant(
        self, desk: Desk, account: Account
    ) -> None:
        grant = desk.sign_in()
        assert grant.refresh_token not in repr(grant)
        assert grant.access_token not in repr(grant)

    def test_the_password_is_left_out_of_the_representation_of_the_command(self) -> None:
        command = SignInCommand(email=KNOWN_EMAIL, password=KNOWN_PASSWORD)
        assert KNOWN_PASSWORD not in repr(command)

    def test_the_address_is_matched_whatever_its_case_and_spacing(
        self, desk: Desk, account: Account
    ) -> None:
        assert desk.sign_in(email=f"  {KNOWN_EMAIL.upper()} ").account.id == account.id

    def test_counter_staff_are_told_the_code_of_their_branch(self, desk: Desk) -> None:
        branch = Branch(id=uuid4(), code="CBD", name="Cape Town CBD", closes_at=CLOSES_AT)
        desk.store.branches[branch.id] = branch
        desk.identity.add_account(
            email="assistant@example.co.za", role=UserRole.COUNTER_STAFF, branch_id=branch.id
        )
        assert desk.sign_in(email="assistant@example.co.za").account.branch_code == "CBD"

    def test_it_writes_a_success_event_naming_the_account_as_the_actor(
        self, desk: Desk, account: Account
    ) -> None:
        desk.sign_in()
        (event,) = desk.audit(LOGIN_SUCCEEDED_ACTION)
        assert event.entity_id == account.id
        assert event.actor_user_id == account.id
        assert event.actor_role is UserRole.CUSTOMER
        assert event.occurred_at == desk.clock.now()

    def test_it_clears_the_failure_count_and_notes_the_sign_in(
        self, desk: Desk, account: Account
    ) -> None:
        desk.sign_in_refused()
        desk.sign_in_refused()
        assert desk.identity.account(account.id).failed_login_count == 2
        desk.sign_in()
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == 0
        assert stored.last_login_at == desk.clock.now()


class TestTheFourRefusalsAreOneRefusal:
    """Wrong password, unknown address, locked and deactivated read the same (BR-46)."""

    def test_each_raises_the_same_error_with_the_same_words_and_no_detail(self, desk: Desk) -> None:
        desk.identity.add_account()
        desk.identity.add_account(email="gone@example.co.za", is_active=False)
        locked = desk.identity.add_account(email="locked@example.co.za")
        desk.identity.account(locked.id).locked_until = desk.clock.now() + LOCKOUT_DURATION
        refusals = [
            desk.sign_in_refused(),
            desk.sign_in_refused(email=UNKNOWN_EMAIL),
            desk.sign_in_refused(email="gone@example.co.za", password=KNOWN_PASSWORD),
            desk.sign_in_refused(email="locked@example.co.za", password=KNOWN_PASSWORD),
        ]
        assert {refusal.message for refusal in refusals} == {INVALID_CREDENTIALS_MESSAGE}
        assert {refusal.code for refusal in refusals} == {"invalid-credentials"}
        assert all(refusal.detail == {} for refusal in refusals)

    def test_every_path_verifies_a_password_exactly_once(self, desk: Desk) -> None:
        desk.identity.add_account()
        desk.identity.add_account(email="gone@example.co.za", is_active=False)
        locked = desk.identity.add_account(email="locked@example.co.za")
        desk.identity.account(locked.id).locked_until = desk.clock.now() + LOCKOUT_DURATION
        desk.sign_in_refused()
        desk.sign_in_refused(email=UNKNOWN_EMAIL)
        desk.sign_in_refused(email="gone@example.co.za", password=KNOWN_PASSWORD)
        desk.sign_in_refused(email="locked@example.co.za", password=KNOWN_PASSWORD)
        desk.sign_in()
        # The real hash for the wrong password and the success, and no hash at
        # all, which the verifier answers with its dummy, for the other three.
        assert desk.passwords.calls == [
            fake_hash(KNOWN_PASSWORD),
            None,
            None,
            None,
            fake_hash(KNOWN_PASSWORD),
        ]

    @pytest.mark.parametrize(
        ("email", "password", "is_active", "locked", "reason"),
        [
            (KNOWN_EMAIL, WRONG_PASSWORD, True, False, "wrong-password"),
            (UNKNOWN_EMAIL, KNOWN_PASSWORD, True, False, "unknown-email"),
            (KNOWN_EMAIL, KNOWN_PASSWORD, False, False, "deactivated"),
            (KNOWN_EMAIL, KNOWN_PASSWORD, True, True, "locked"),
        ],
    )
    def test_the_reason_is_kept_in_the_audit_trail_and_nowhere_the_caller_sees(
        self, desk: Desk, email: str, password: str, is_active: bool, locked: bool, reason: str
    ) -> None:
        account = desk.identity.add_account(is_active=is_active)
        if locked:
            desk.identity.account(account.id).locked_until = desk.clock.now() + LOCKOUT_DURATION
        refusal = desk.sign_in_refused(email=email, password=password)
        (event,) = desk.audit(LOGIN_FAILED_ACTION)
        assert event.after_state is not None
        assert event.after_state["reason"] == reason
        assert event.actor_user_id is None
        assert event.entity_id == (UNKNOWN_ACCOUNT_ID if email == UNKNOWN_EMAIL else account.id)
        assert reason not in refusal.message

    def test_a_deactivated_or_locked_account_does_not_gain_failures(self, desk: Desk) -> None:
        gone = desk.identity.add_account(is_active=False)
        desk.sign_in_refused(password=WRONG_PASSWORD)
        assert desk.identity.account(gone.id).failed_login_count == 0
