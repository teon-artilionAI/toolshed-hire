"""The configured sign in limits reach the use case, and through it the route (C-17).

The two limits are settings, and `app/api/identity_deps.py` is where they are
handed to the sign in use case. These tests pin that hand over at each step.
The rules are built from a configuration, the dependency passes them on, and
the route then throttles at the configured limit and not at the default.

The process the suite runs in keeps the default limits. So the HTTP tests give
the real application the rules a process configured with other limits would
have built, in place of its own, and take them away again afterwards.

bcrypt is swapped for a verifier that refuses everything, because these tests
are about counting.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.identity_deps import get_login_rules, get_sign_in_use_case, login_rules_for
from app.application.identity.sign_in import (
    LOGIN_ATTEMPTS_PER_ADDRESS,
    LOGIN_ATTEMPTS_PER_EMAIL,
    LOGIN_WINDOW,
    LoginThrottleRules,
    SignInCommand,
)
from app.config import Environment, settings
from app.domain.errors import InvalidCredentials, TooManyAttempts
from app.main import app as production_app
from tests.support.identity_desk import Desk
from tests.support.memory_identity import IdentityMemoryUnitOfWork
from tests.support.request_probe import settings_for
from tests.support.sessions import (
    UNKNOWN_EMAIL,
    WRONG_PASSWORD,
    session_client,
    sign_in,
    without_bcrypt,
)

RETRY_AFTER_HEADER: Final[str] = "Retry-After"
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
# Limits a process could be configured with. Both are stricter than the
# defaults, so they are ones every environment accepts.
CONFIGURED_EMAIL_LIMIT: Final[int] = 3
CONFIGURED_ADDRESS_LIMIT: Final[int] = 5


@pytest.fixture
def no_bcrypt() -> Iterator[None]:
    """Swap the password verifier of the real application for one that costs nothing."""
    with without_bcrypt():
        yield


@pytest.fixture
def configured_rules() -> LoginThrottleRules:
    """Return the rules the composition root builds from a configuration with other limits."""
    return login_rules_for(
        settings_for(
            Environment.PRODUCTION,
            LOGIN_ATTEMPTS_PER_EMAIL=str(CONFIGURED_EMAIL_LIMIT),
            LOGIN_ATTEMPTS_PER_ADDRESS=str(CONFIGURED_ADDRESS_LIMIT),
        )
    )


@pytest.fixture
def configured_application(configured_rules: LoginThrottleRules) -> Iterator[None]:
    """Run the real application as a process configured with the other limits would."""
    production_app.dependency_overrides[get_login_rules] = lambda: configured_rules
    try:
        yield
    finally:
        production_app.dependency_overrides.pop(get_login_rules, None)


class TestTheRulesAreBuiltFromTheSettings:
    """What the composition root makes of the two settings."""

    def test_the_configured_limits_are_not_the_defaults(self) -> None:
        assert CONFIGURED_EMAIL_LIMIT != LOGIN_ATTEMPTS_PER_EMAIL
        assert CONFIGURED_ADDRESS_LIMIT != LOGIN_ATTEMPTS_PER_ADDRESS

    def test_each_rule_takes_its_limit_from_its_own_setting(
        self, configured_rules: LoginThrottleRules
    ) -> None:
        assert configured_rules.email.limit == CONFIGURED_EMAIL_LIMIT
        assert configured_rules.address.limit == CONFIGURED_ADDRESS_LIMIT

    def test_the_window_is_not_configured_and_stays_fifteen_minutes(
        self, configured_rules: LoginThrottleRules
    ) -> None:
        assert configured_rules.email.window == configured_rules.address.window == LOGIN_WINDOW

    def test_the_rules_of_the_process_carry_the_limits_it_loaded(self) -> None:
        rules = get_login_rules()
        assert rules == login_rules_for(settings)
        assert (rules.email.limit, rules.address.limit) == (
            settings.login_attempts_per_email,
            settings.login_attempts_per_address,
        )


class TestTheDependencyHandsTheRulesOver:
    """The sign in use case the dependency returns counts against the rules it was given."""

    def test_the_use_case_throttles_at_the_configured_limit(
        self, configured_rules: LoginThrottleRules
    ) -> None:
        desk = Desk()
        use_case = get_sign_in_use_case(
            IdentityMemoryUnitOfWork(desk.store, desk.identity),
            desk.clock,
            desk.passwords,
            desk.tokens,
            desk.throttle,
            configured_rules,
        )
        command = SignInCommand(email=UNKNOWN_EMAIL, password=WRONG_PASSWORD)
        for _ in range(CONFIGURED_EMAIL_LIMIT):
            with pytest.raises(InvalidCredentials):
                use_case.execute(command)
        with pytest.raises(TooManyAttempts):
            use_case.execute(command)


@pytest.mark.usefixtures("no_bcrypt", "configured_application")
class TestTheRouteThrottlesAtTheConfiguredLimits:
    """Through HTTP, the wait comes after the configured number of attempts."""

    def test_one_address_is_told_to_wait_after_the_configured_limit(
        self, auth_client: TestClient
    ) -> None:
        for _ in range(CONFIGURED_EMAIL_LIMIT):
            assert sign_in(auth_client, UNKNOWN_EMAIL).status_code == status.HTTP_401_UNAUTHORIZED
        throttled = sign_in(auth_client, UNKNOWN_EMAIL)
        assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert throttled.headers[RETRY_AFTER_HEADER] == str(int(LOGIN_WINDOW.total_seconds()))

    def test_one_client_is_told_to_wait_after_the_configured_limit(self, session: Session) -> None:
        with session_client(session, client_address=CLIENT_ADDRESS) as client:
            for number in range(CONFIGURED_ADDRESS_LIMIT):
                response = sign_in(client, f"guess{number}@toolshedhire.co.za")
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
            throttled = sign_in(client, "one.more@toolshedhire.co.za")
        assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
