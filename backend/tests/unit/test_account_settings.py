"""The settings the account routes add, which are their seven limits and the frontend origin.

Each limit is an environment variable with the default the application layer
states. None may be below one, and outside development and test none may be
raised above its default, exactly as for the two sign in limits (C-17). The
rules they make keep their names and their windows whatever the limits.

The frontend origin is where the links in the account messages point. Left
unset it is the one origin in `CORS_ORIGINS`, which is how the deployed
environments are set up today. A deployed environment refuses an origin that
is not `https` or that names this machine.
"""

from __future__ import annotations

from typing import Final

import pytest
from pydantic import ValidationError

from app.api.account_deps import account_rules_for
from app.application.identity.attempts import (
    ACCOUNT_ATTEMPT_WINDOW,
    ACCOUNT_MAIL_WINDOW,
    DEFAULT_ACCOUNT_RULES,
    UNKNOWN_ADDRESS_SUBJECT,
    address_subject,
)
from app.application.identity.sessions import ClientDetails
from app.config import Environment
from app.config_checks import DEVELOPMENT_FRONTEND_ORIGIN
from app.config_limits import ATTEMPT_LIMIT_SETTINGS
from tests.support.request_probe import DEPLOYED_FRONTEND_ORIGIN, settings_for

ACCOUNT_LIMITS: Final[list[tuple[str, str, int]]] = [
    setting for setting in ATTEMPT_LIMIT_SETTINGS if not setting[0].startswith("LOGIN_")
]
DEPLOYED_ENVIRONMENTS: Final[list[Environment]] = [Environment.STAGING, Environment.PRODUCTION]
SITE: Final[str] = "https://www.example.co.za"


@pytest.fixture(autouse=True)
def no_limit_or_origin_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Take every variable these tests set out of the environment first."""
    for variable, _attribute, _default in ATTEMPT_LIMIT_SETTINGS:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)


class TestTheSevenLimits:
    """Read from the environment, never below one, and never raised where it is deployed."""

    def test_there_is_one_setting_for_each_rule(self) -> None:
        assert [variable for variable, _attribute, _default in ACCOUNT_LIMITS] == [
            "REGISTER_ATTEMPTS_PER_EMAIL",
            "REGISTER_ATTEMPTS_PER_ADDRESS",
            "VERIFICATION_ATTEMPTS_PER_ADDRESS",
            "VERIFICATION_RESENDS_PER_ACCOUNT",
            "RESET_REQUESTS_PER_EMAIL",
            "RESET_REQUESTS_PER_ADDRESS",
            "RESET_COMPLETIONS_PER_ADDRESS",
        ]

    def test_left_unset_each_limit_is_its_default_and_the_rules_are_the_defaults(self) -> None:
        loaded = settings_for(Environment.TEST)
        for _variable, attribute, default in ACCOUNT_LIMITS:
            assert getattr(loaded, attribute) == default
        assert account_rules_for(loaded) == DEFAULT_ACCOUNT_RULES

    @pytest.mark.parametrize(("variable", "attribute", "default"), ACCOUNT_LIMITS)
    def test_each_is_read_from_its_variable(
        self, variable: str, attribute: str, default: int
    ) -> None:
        assert getattr(settings_for(Environment.TEST, **{variable: "2"}), attribute) == 2

    @pytest.mark.parametrize(("variable", "attribute", "default"), ACCOUNT_LIMITS)
    def test_none_may_be_below_one(self, variable: str, attribute: str, default: int) -> None:
        with pytest.raises(ValidationError, match=f"{variable} must be at least 1, got 0"):
            settings_for(Environment.TEST, **{variable: "0"})

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    @pytest.mark.parametrize(("variable", "attribute", "default"), ACCOUNT_LIMITS)
    def test_none_may_be_raised_where_the_service_is_deployed(
        self, environment: Environment, variable: str, attribute: str, default: int
    ) -> None:
        with pytest.raises(ValidationError, match=f"{variable} must not be above its default"):
            settings_for(environment, **{variable: str(default + 1)})
        lowered = settings_for(environment, **{variable: str(max(default - 1, 1))})
        assert getattr(lowered, attribute) == max(default - 1, 1)

    def test_a_configured_limit_reaches_its_rule_and_keeps_the_name_and_window(self) -> None:
        configured = settings_for(
            Environment.TEST, REGISTER_ATTEMPTS_PER_EMAIL="2", RESET_REQUESTS_PER_ADDRESS="3"
        )
        rules = account_rules_for(configured)
        assert rules.register_email.limit == 2
        assert rules.reset_request_address.limit == 3
        assert rules.register_email.name == DEFAULT_ACCOUNT_RULES.register_email.name
        assert rules.register_email.window == ACCOUNT_MAIL_WINDOW
        assert rules.reset_request_address.window == ACCOUNT_ATTEMPT_WINDOW

    def test_the_start_up_log_shows_every_limit_as_a_number(self) -> None:
        shown = settings_for(Environment.TEST).redacted()
        for _variable, attribute, default in ACCOUNT_LIMITS:
            assert shown[attribute] == default

    def test_clients_with_no_known_address_share_one_subject(self) -> None:
        assert address_subject(ClientDetails()) == UNKNOWN_ADDRESS_SUBJECT


class TestTheFrontendOrigin:
    """Where the links in the account messages point."""

    def test_it_is_the_variable_when_it_is_set_without_a_trailing_slash(self) -> None:
        loaded = settings_for(Environment.PRODUCTION, FRONTEND_ORIGIN=f"{SITE}/")
        assert loaded.frontend_origin == SITE

    def test_unset_it_is_the_one_cors_origin_as_in_a_deployment_today(self) -> None:
        loaded = settings_for(Environment.PRODUCTION, FRONTEND_ORIGIN="", CORS_ORIGINS=SITE)
        assert loaded.frontend_origin == SITE

    def test_unset_in_development_it_is_the_vite_dev_server(self) -> None:
        loaded = settings_for(Environment.DEVELOPMENT, FRONTEND_ORIGIN="")
        assert loaded.frontend_origin == DEVELOPMENT_FRONTEND_ORIGIN == "http://localhost:5173"

    def test_the_test_settings_of_a_deployed_environment_carry_one(self) -> None:
        assert settings_for(Environment.STAGING).frontend_origin == DEPLOYED_FRONTEND_ORIGIN

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_a_deployed_service_will_not_start_without_knowing_it(
        self, environment: Environment
    ) -> None:
        with pytest.raises(ValidationError, match="FRONTEND_ORIGIN is not set"):
            settings_for(environment, FRONTEND_ORIGIN="", CORS_ORIGINS=f"{SITE},https://b.example")

    @pytest.mark.parametrize(
        "origin", ["http://www.example.co.za", "https://localhost:5173", "https://127.0.0.1"]
    )
    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_a_deployed_service_wants_a_public_https_address(
        self, environment: Environment, origin: str
    ) -> None:
        with pytest.raises(ValidationError, match="public https address"):
            settings_for(environment, FRONTEND_ORIGIN=origin)

    @pytest.mark.parametrize(
        "origin", ["www.example.co.za", "ftp://example.co.za", f"{SITE}/app", f"{SITE}/?a=b"]
    )
    def test_anything_but_an_origin_is_refused_everywhere(self, origin: str) -> None:
        with pytest.raises(ValidationError, match="must be an origin"):
            settings_for(Environment.TEST, FRONTEND_ORIGIN=origin)

    def test_development_accepts_the_local_dev_server(self) -> None:
        loaded = settings_for(Environment.TEST, FRONTEND_ORIGIN="http://localhost:5173")
        assert loaded.frontend_origin == "http://localhost:5173"

    def test_the_start_up_log_shows_it(self) -> None:
        assert settings_for(Environment.PRODUCTION).redacted()["frontend_origin"] == (
            DEPLOYED_FRONTEND_ORIGIN
        )
