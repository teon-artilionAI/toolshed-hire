"""The start-up checks, and the environments they apply to.

`ENVIRONMENT` accepts four values. Development and test are relaxed, which
means the placeholder secrets from `.env.example` are tolerated. Staging and
production are not, and staging is held to exactly the checks production is. A
staging service that starts on a known signing key is a deployed service with a
known signing key, whatever it is called.

Every check here is run against both deployed environments with one
parametrised test, so the two cannot drift apart without a test failing.
"""

from __future__ import annotations

import traceback
from typing import Final

import pytest
from pydantic import ValidationError

from app.config import (
    DEVELOPMENT_DATABASE_URL,
    DEVELOPMENT_JWT_SECRET,
    LOCAL_REVISION,
    MINIMUM_JWT_SECRET_LENGTH,
    ConfigurationError,
    Environment,
    load_settings,
)
from tests.support.request_probe import DEPLOYED_DATABASE_URL, DEPLOYED_JWT_SECRET, settings_for

RELAXED_ENVIRONMENTS: Final[list[Environment]] = [Environment.DEVELOPMENT, Environment.TEST]
DEPLOYED_ENVIRONMENTS: Final[list[Environment]] = [Environment.STAGING, Environment.PRODUCTION]
SHORT_JWT_SECRET: Final[str] = "x" * (MINIMUM_JWT_SECRET_LENGTH - 1)
CLOUD_RUN_REVISION: Final[str] = "toolshed-hire-api-00042-xuv"
REVISION_VARIABLE: Final[str] = "K_REVISION"
# pydantic shortens the input it quotes and keeps its two ends, so a leak shows
# as the head or the tail of the secret and never as the whole of it.
SECRET_TAIL_LENGTH: Final[int] = 12


class TestTheEnvironmentValues:
    """The four accepted values, and which of them are relaxed."""

    def test_the_accepted_values_are_exactly_these_four(self) -> None:
        assert {environment.value for environment in Environment} == {
            "development",
            "test",
            "staging",
            "production",
        }

    @pytest.mark.parametrize("environment", RELAXED_ENVIRONMENTS)
    def test_development_and_test_are_relaxed(self, environment: Environment) -> None:
        assert environment.is_relaxed

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_staging_and_production_are_not_relaxed(self, environment: Environment) -> None:
        assert not environment.is_relaxed

    def test_a_value_outside_the_four_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            settings_for(Environment.TEST, ENVIRONMENT="preview")


class TestStagingIsHeldToTheProductionChecks:
    """Each start-up check, against staging and production alike."""

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_real_values_are_accepted(self, environment: Environment) -> None:
        loaded = settings_for(environment)
        assert loaded.environment is environment
        assert loaded.jwt_secret == DEPLOYED_JWT_SECRET
        assert loaded.database_url == DEPLOYED_DATABASE_URL

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_the_placeholder_signing_key_is_refused(self, environment: Environment) -> None:
        with pytest.raises(ValidationError, match="JWT_SECRET is still the .env.example"):
            settings_for(environment, JWT_SECRET=DEVELOPMENT_JWT_SECRET)

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_a_short_signing_key_is_refused(self, environment: Environment) -> None:
        with pytest.raises(ValidationError, match="the minimum is"):
            settings_for(environment, JWT_SECRET=SHORT_JWT_SECRET)

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_the_development_database_is_refused(self, environment: Environment) -> None:
        with pytest.raises(ValidationError, match="local development database"):
            settings_for(environment, DATABASE_URL=DEVELOPMENT_DATABASE_URL)

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    def test_the_refusal_names_the_environment(self, environment: Environment) -> None:
        with pytest.raises(ValidationError) as refusal:
            settings_for(environment, JWT_SECRET=SHORT_JWT_SECRET)
        assert f"Refusing to start in environment {environment.value!r}" in str(refusal.value)

    @pytest.mark.parametrize("environment", RELAXED_ENVIRONMENTS)
    def test_the_placeholders_are_tolerated_where_nothing_is_deployed(
        self, environment: Environment
    ) -> None:
        loaded = settings_for(
            environment,
            JWT_SECRET=DEVELOPMENT_JWT_SECRET,
            DATABASE_URL=DEVELOPMENT_DATABASE_URL,
        )
        assert loaded.environment is environment


class TestAFailedStartNamesTheFaultAndNotTheSecret:
    """A process that refuses to start writes its reason to the log in full.

    The likeliest failed start is a first deployment with one value right and
    one wrong. The reason has to name the wrong one without repeating the right
    one, and that includes the traceback Python prints as the process dies.
    """

    @pytest.fixture
    def half_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Give the process a real signing key and the development database."""
        monkeypatch.setenv("ENVIRONMENT", Environment.PRODUCTION.value)
        monkeypatch.setenv("JWT_SECRET", DEPLOYED_JWT_SECRET)
        monkeypatch.setenv("DATABASE_URL", DEVELOPMENT_DATABASE_URL)

    @pytest.mark.usefixtures("half_configured")
    def test_the_reason_names_the_setting_that_is_wrong(self) -> None:
        with pytest.raises(ConfigurationError, match="DATABASE_URL still points at the local"):
            load_settings()

    @pytest.mark.usefixtures("half_configured")
    def test_neither_the_message_nor_the_traceback_repeats_the_signing_key(self) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            load_settings()
        printed = "".join(traceback.format_exception(refusal.value))
        assert DEPLOYED_JWT_SECRET[-SECRET_TAIL_LENGTH:] not in printed
        assert DEPLOYED_JWT_SECRET[:SECRET_TAIL_LENGTH] not in printed

    def test_a_connection_string_of_the_wrong_kind_is_not_repeated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "mysql://owner:a_wrong_kind_password@db.internal/tsh")
        with pytest.raises(ConfigurationError) as refusal:
            load_settings()
        printed = "".join(traceback.format_exception(refusal.value))
        assert "the scheme 'mysql'" in printed
        assert "a_wrong_kind_password" not in printed
        assert "owner" not in printed


class TestTheRevision:
    """`K_REVISION` is set by Cloud Run and by nothing else."""

    def test_it_is_local_when_the_variable_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(REVISION_VARIABLE, raising=False)
        assert settings_for(Environment.TEST).revision == LOCAL_REVISION

    def test_it_is_read_from_the_variable_cloud_run_sets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REVISION_VARIABLE, CLOUD_RUN_REVISION)
        assert settings_for(Environment.PRODUCTION).revision == CLOUD_RUN_REVISION

    def test_a_blank_value_is_reported_as_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(REVISION_VARIABLE, "   ")
        assert settings_for(Environment.TEST).revision == LOCAL_REVISION


class TestTheRedactedConfiguration:
    """What the start-up log shows of the configuration."""

    def test_it_names_the_environment_and_the_revision(self) -> None:
        shown = settings_for(Environment.STAGING).redacted()
        assert shown["environment"] == "staging"
        assert shown["revision"] == LOCAL_REVISION

    def test_it_holds_neither_the_signing_key_nor_the_database_credentials(self) -> None:
        shown = str(settings_for(Environment.PRODUCTION).redacted())
        assert DEPLOYED_JWT_SECRET not in shown
        assert "not_a_real_password" not in shown
        assert "toolshed_app" not in shown

    def test_no_key_is_one_the_log_filter_would_blank_out(self) -> None:
        # The filter replaces the value of any key that looks like a secret.
        # "set" and a lifetime in minutes are facts worth reading in the log.
        shown = settings_for(Environment.PRODUCTION, ACCESS_TOKEN_MINUTES="30").redacted()
        assert shown["jwt_signing_key"] == "set"
        assert shown["access_lifetime_minutes"] == 30
