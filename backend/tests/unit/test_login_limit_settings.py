"""The two sign in limits as settings (C-17).

`LOGIN_ATTEMPTS_PER_EMAIL` and `LOGIN_ATTEMPTS_PER_ADDRESS` say how many sign
in attempts one fifteen minute window allows. Left unset they are the limits
the design document sets. Neither may be below one in any environment. In
staging and production neither may be above its default, so a deployed service
can be made stricter than the design and never looser. Development and test
take any value from the floor up, which is what the browser tests rely on.

Every check is run against both variables with one parametrised test, so the
two cannot drift apart without a test failing.
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Final

import pytest
from pydantic import ValidationError

from app.application.identity.sign_in import LOGIN_ATTEMPTS_PER_ADDRESS, LOGIN_ATTEMPTS_PER_EMAIL
from app.config import ConfigurationError, Environment, Settings, load_settings
from app.config_checks import MINIMUM_LOGIN_ATTEMPTS
from app.log_redaction import REDACTED_PLACEHOLDER
from tests.support.log_capture import LogCapture
from tests.support.request_probe import DEPLOYED_DATABASE_URL, DEPLOYED_JWT_SECRET, settings_for

logger = logging.getLogger("app.tests.login_limit_settings")

RELAXED_ENVIRONMENTS: Final[list[Environment]] = [Environment.DEVELOPMENT, Environment.TEST]
DEPLOYED_ENVIRONMENTS: Final[list[Environment]] = [Environment.STAGING, Environment.PRODUCTION]
EVERY_ENVIRONMENT: Final[list[Environment]] = list(Environment)
VALUES_BELOW_THE_FLOOR: Final[list[int]] = [0, -1]
# pydantic shortens the input it quotes and keeps its two ends, so a leak shows
# as the head or the tail of the secret and never as the whole of it.
SECRET_TAIL_LENGTH: Final[int] = 12
LOG_MESSAGE: Final[str] = "test.configuration_resolved"


@dataclass(frozen=True)
class Limit:
    """One of the two settings, as a test needs to know it.

    Attributes:
        variable: The environment variable the setting is read from.
        attribute: The attribute of `Settings` that holds it, which is also the
            key it is reported under in the start-up log.
        default: The limit when the variable is unset.

    """

    variable: str
    attribute: str
    default: int

    def loaded_by(self, loaded: Settings) -> int:
        """Return the value of this setting in a loaded configuration."""
        return int(getattr(loaded, self.attribute))


PER_EMAIL: Final[Limit] = Limit(
    "LOGIN_ATTEMPTS_PER_EMAIL", "login_attempts_per_email", LOGIN_ATTEMPTS_PER_EMAIL
)
PER_ADDRESS: Final[Limit] = Limit(
    "LOGIN_ATTEMPTS_PER_ADDRESS", "login_attempts_per_address", LOGIN_ATTEMPTS_PER_ADDRESS
)
BOTH_LIMITS: Final[list[Limit]] = [PER_EMAIL, PER_ADDRESS]


def settings_with(environment: Environment, limit: Limit, value: int) -> Settings:
    """Build the settings of an environment with one of the two limits set."""
    return settings_for(environment, **{limit.variable: str(value)})


@pytest.fixture(autouse=True)
def neither_variable_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Take both variables out of the environment, so each test sets what it means to."""
    for limit in BOTH_LIMITS:
        monkeypatch.delenv(limit.variable, raising=False)


class TestTheDefaults:
    """Left unset, the limits are the ones the design document sets."""

    @pytest.mark.parametrize("environment", EVERY_ENVIRONMENT)
    def test_they_are_ten_and_thirty_when_neither_variable_is_set(
        self, environment: Environment
    ) -> None:
        loaded = settings_for(environment)
        assert (loaded.login_attempts_per_email, loaded.login_attempts_per_address) == (10, 30)

    def test_they_are_the_limits_the_use_case_falls_back_to(self) -> None:
        loaded = settings_for(Environment.TEST)
        assert [limit.loaded_by(loaded) for limit in BOTH_LIMITS] == [
            LOGIN_ATTEMPTS_PER_EMAIL,
            LOGIN_ATTEMPTS_PER_ADDRESS,
        ]


class TestEachVariableIsRead:
    """A value in the environment becomes the limit, and only that limit."""

    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_it_is_read_from_the_environment(
        self, limit: Limit, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(limit.variable, "4")
        loaded = settings_for(Environment.TEST)
        assert limit.loaded_by(loaded) == 4
        (other,) = [candidate for candidate in BOTH_LIMITS if candidate is not limit]
        assert other.loaded_by(loaded) == other.default

    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_that_is_not_a_whole_number_is_refused_by_name(self, limit: Limit) -> None:
        with pytest.raises(ValidationError, match=limit.variable):
            settings_for(Environment.TEST, **{limit.variable: "ten"})


class TestTheFloor:
    """Neither limit may be below one, wherever the process runs."""

    def test_the_floor_is_one(self) -> None:
        assert MINIMUM_LOGIN_ATTEMPTS == 1

    @pytest.mark.parametrize("value", VALUES_BELOW_THE_FLOOR)
    @pytest.mark.parametrize("environment", EVERY_ENVIRONMENT)
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_below_it_is_refused_and_the_variable_is_named(
        self, limit: Limit, environment: Environment, value: int
    ) -> None:
        with pytest.raises(ValidationError, match=f"{limit.variable} must be at least 1, got"):
            settings_with(environment, limit, value)

    @pytest.mark.parametrize("environment", EVERY_ENVIRONMENT)
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_on_it_is_accepted(self, limit: Limit, environment: Environment) -> None:
        loaded = settings_with(environment, limit, MINIMUM_LOGIN_ATTEMPTS)
        assert limit.loaded_by(loaded) == MINIMUM_LOGIN_ATTEMPTS

    def test_two_values_below_it_are_both_named_in_one_refusal(self) -> None:
        with pytest.raises(ValidationError) as refusal:
            settings_for(Environment.TEST, **{PER_EMAIL.variable: "0", PER_ADDRESS.variable: "0"})
        assert f"{PER_EMAIL.variable} must be at least 1" in str(refusal.value)
        assert f"{PER_ADDRESS.variable} must be at least 1" in str(refusal.value)


class TestADeployedServiceCanOnlyBeMadeStricter:
    """Staging and production refuse a limit above its default. The other two do not."""

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_above_the_default_is_refused(
        self, limit: Limit, environment: Environment
    ) -> None:
        raised = limit.default + 1
        with pytest.raises(ValidationError) as refusal:
            settings_with(environment, limit, raised)
        assert (
            f"{limit.variable} must not be above its default of {limit.default} in "
            f"environment {environment.value!r}, got {raised}."
        ) in str(refusal.value)

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_equal_to_the_default_is_accepted(
        self, limit: Limit, environment: Environment
    ) -> None:
        assert limit.loaded_by(settings_with(environment, limit, limit.default)) == limit.default

    @pytest.mark.parametrize("environment", DEPLOYED_ENVIRONMENTS)
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_lower_value_is_accepted(self, limit: Limit, environment: Environment) -> None:
        lowered = limit.default - 1
        assert limit.loaded_by(settings_with(environment, limit, lowered)) == lowered

    @pytest.mark.parametrize("environment", RELAXED_ENVIRONMENTS)
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_above_the_default_is_accepted_where_nothing_is_deployed(
        self, limit: Limit, environment: Environment
    ) -> None:
        raised = limit.default * 10
        assert limit.loaded_by(settings_with(environment, limit, raised)) == raised


class TestAFailedStartNamesTheLimit:
    """What the process says as it refuses to start on a limit it cannot use."""

    @pytest.fixture
    def deployed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Give the process everything production needs, and nothing about the limits."""
        monkeypatch.setenv("ENVIRONMENT", Environment.PRODUCTION.value)
        monkeypatch.setenv("JWT_SECRET", DEPLOYED_JWT_SECRET)
        monkeypatch.setenv("DATABASE_URL", DEPLOYED_DATABASE_URL)

    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_value_below_the_floor_stops_the_start(
        self, limit: Limit, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(limit.variable, "0")
        with pytest.raises(ConfigurationError, match=f"{limit.variable} must be at least 1"):
            load_settings()

    @pytest.mark.usefixtures("deployed")
    @pytest.mark.parametrize("limit", BOTH_LIMITS)
    def test_a_raised_limit_stops_a_deployed_start_and_repeats_no_secret(
        self, limit: Limit, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(limit.variable, str(limit.default + 1))
        with pytest.raises(ConfigurationError) as refusal:
            load_settings()
        printed = "".join(traceback.format_exception(refusal.value))
        assert f"{limit.variable} must not be above its default of {limit.default}" in printed
        assert "environment 'production'" in printed
        assert DEPLOYED_JWT_SECRET[-SECRET_TAIL_LENGTH:] not in printed
        assert DEPLOYED_JWT_SECRET[:SECRET_TAIL_LENGTH] not in printed
        assert "not_a_real_password" not in printed

    def test_the_refusal_lists_both_variables_among_those_it_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PER_EMAIL.variable, "0")
        with pytest.raises(ConfigurationError) as refusal:
            load_settings()
        attempted = str(refusal.value).split("Cause:")[0]
        assert PER_EMAIL.variable in attempted
        assert PER_ADDRESS.variable in attempted


class TestWhatTheStartUpLogShows:
    """The two limits the process loaded, as numbers an operator can read."""

    def test_the_redacted_configuration_holds_both_limits_as_numbers(self) -> None:
        shown = settings_for(
            Environment.TEST, **{PER_EMAIL.variable: "4", PER_ADDRESS.variable: "7"}
        ).redacted()
        assert shown[PER_EMAIL.attribute] == 4
        assert shown[PER_ADDRESS.attribute] == 7

    def test_the_log_filter_writes_them_and_not_the_placeholder(
        self, application_log: LogCapture
    ) -> None:
        # The filter blanks the value of any key that looks like a secret, and
        # these two are facts worth reading in the log.
        loaded = settings_for(
            Environment.TEST, **{PER_EMAIL.variable: "4", PER_ADDRESS.variable: "7"}
        )
        logger.info(LOG_MESSAGE, extra=loaded.redacted())
        entry = application_log.only(LOG_MESSAGE)
        assert entry[PER_EMAIL.attribute] == 4
        assert entry[PER_ADDRESS.attribute] == 7
        assert REDACTED_PLACEHOLDER not in entry.values()
