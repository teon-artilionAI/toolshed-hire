"""The three session use cases, wired over the in memory stores for a unit test.

A test of signing in, refreshing or signing out needs the same handful of
things every time, which are two stores, a clock that stands still, a password
verifier that counts and a token issuer that issues nothing real. `Desk`
holds them and wires each use case the way the composition root does, with a
unit of work of its own over the same stores.

The helpers that end in `refused` assert the refusal and hand it back, so a
test that is about what a refusal leaves behind does not repeat the `raises`
block every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import Final

import pytest

from app.application.identity.refresh_session import (
    RefreshSessionCommand,
    RefreshSessionUseCase,
)
from app.application.identity.sessions import ClientDetails, SessionGrant
from app.application.identity.sign_in import (
    DEFAULT_LOGIN_RULES,
    LoginThrottleRules,
    SignInCommand,
    SignInUseCase,
)
from app.application.identity.sign_out import SignOutCommand, SignOutUseCase
from app.application.throttle import Throttle
from app.domain.audit import AuditEvent
from app.domain.enums import RevokeReason
from app.domain.errors import InvalidCredentials, SessionExpired
from tests.support.clock import FixedClock
from tests.support.memory import MemoryStore
from tests.support.memory_identity import (
    KNOWN_EMAIL,
    KNOWN_PASSWORD,
    CountingPasswordVerifier,
    FakeAccessTokenIssuer,
    IdentityMemoryUnitOfWork,
    IdentityStore,
)

WRONG_PASSWORD: Final[str] = "not-the-password-at-all"
UNKNOWN_EMAIL: Final[str] = "nobody.at.all@example.co.za"
CLIENT: Final[ClientDetails] = ClientDetails(
    address=ip_address("203.0.113.9"), user_agent="A browser"
)
FAKE_SALT: Final[str] = "made-up-salt-for-this-test"


@dataclass
class Desk:
    """Everything one session test needs, wired the way the composition root wires it."""

    store: MemoryStore = field(default_factory=MemoryStore)
    identity: IdentityStore = field(default_factory=IdentityStore)
    clock: FixedClock = field(default_factory=FixedClock)
    passwords: CountingPasswordVerifier = field(default_factory=CountingPasswordVerifier)
    tokens: FakeAccessTokenIssuer = field(default_factory=FakeAccessTokenIssuer)
    throttle: Throttle = field(default_factory=lambda: Throttle(FAKE_SALT))
    rules: LoginThrottleRules = DEFAULT_LOGIN_RULES

    def _uow(self) -> IdentityMemoryUnitOfWork:
        """Return a new unit of work over the two stores."""
        return IdentityMemoryUnitOfWork(self.store, self.identity)

    def sign_in(
        self,
        email: str = KNOWN_EMAIL,
        password: str = KNOWN_PASSWORD,
        client: ClientDetails = CLIENT,
    ) -> SessionGrant:
        """Run the sign in use case once."""
        use_case = SignInUseCase(
            self._uow(), self.clock, self.passwords, self.tokens, self.throttle, self.rules
        )
        return use_case.execute(SignInCommand(email=email, password=password, client=client))

    def sign_in_refused(
        self, email: str = KNOWN_EMAIL, password: str = WRONG_PASSWORD
    ) -> InvalidCredentials:
        """Run a sign in that must be refused, and return the refusal."""
        with pytest.raises(InvalidCredentials) as refusal:
            self.sign_in(email, password)
        return refusal.value

    def refresh(self, token: str | None) -> SessionGrant:
        """Run the refresh use case once."""
        use_case = RefreshSessionUseCase(self._uow(), self.clock, self.tokens)
        return use_case.execute(RefreshSessionCommand(presented_token=token, client=CLIENT))

    def refresh_refused(self, token: str | None) -> SessionExpired:
        """Run a refresh that must be refused, and return the refusal."""
        with pytest.raises(SessionExpired) as refusal:
            self.refresh(token)
        return refusal.value

    def sign_out(self, token: str | None) -> int:
        """Run the sign out use case once and return how many sessions it revoked."""
        return SignOutUseCase(self._uow(), self.clock).execute(
            SignOutCommand(presented_token=token)
        )

    def audit(self, action: str) -> list[AuditEvent]:
        """Return the committed audit events of one action, oldest first."""
        return [event for event in self.store.committed.audit_events if event.action == action]

    def revoke_reasons(self) -> list[RevokeReason | None]:
        """Return why each committed session was revoked, in the order they were opened."""
        sessions = sorted(
            self.identity.committed.sessions.values(), key=lambda session: session.issued_at
        )
        return [session.revoked_reason for session in sessions]


__all__ = ["CLIENT", "UNKNOWN_EMAIL", "WRONG_PASSWORD", "Desk"]
