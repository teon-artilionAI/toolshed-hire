"""Process configuration for the Toolshed Hire backend.

Configuration is read once from the environment at import time. If a secret is
missing or is still the development placeholder while the process claims to be
running outside development, the import fails immediately with an actionable
message. Starting a production process on a known default secret is a security
hole that would otherwise stay invisible until it is exploited.
"""

from __future__ import annotations

import logging

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from app.config_checks import (
    FRONTEND_ORIGIN_VARIABLE,
    check_attempt_limits,
    describe_failure,
    force_psycopg_driver,
    resolve_frontend_origin,
)
from app.config_clock import ClockSettings, check_test_business_time
from app.config_environment import ConfigurationError as ConfigurationError
from app.config_environment import Environment as Environment
from app.config_limits import AttemptLimitSettings

logger = logging.getLogger(__name__)

# The placeholder secret shipped in .env.example. Recognised by name so that a
# forgotten copy and paste cannot reach a deployed environment.
DEVELOPMENT_JWT_SECRET = "development-only-insecure-secret-do-not-deploy"
DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://toolshed:toolshed@localhost:5432/toolshed"

MINIMUM_JWT_SECRET_LENGTH = 32
MINIMUM_ACCESS_TOKEN_MINUTES = 1
MAXIMUM_ACCESS_TOKEN_MINUTES = 60
SUPPORTED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
# Reported as the revision when the process is not running on Cloud Run.
LOCAL_REVISION = "local"
# What RESEND_API_KEY holds in a deployment whose email account does not exist
# yet. It is treated exactly like an unset key, so the service starts and takes
# bookings and every confirmation is recorded as not sent.
RESEND_API_KEY_PLACEHOLDER = "not-configured-yet"
# The sender Resend accepts without a verified domain.
DEFAULT_EMAIL_FROM = "Toolshed Hire <onboarding@resend.dev>"


class Settings(AttemptLimitSettings, ClockSettings):
    """Validated configuration values, one field per environment variable.

    The attempt limits are declared in `AttemptLimitSettings`, and the test
    clock in `ClockSettings`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT",
        description="development, test, staging or production",
    )
    database_url: str = Field(
        default=DEVELOPMENT_DATABASE_URL,
        validation_alias="DATABASE_URL",
        description="SQLAlchemy DSN for the pooled PostgreSQL endpoint",
    )
    jwt_secret: str = Field(
        default=DEVELOPMENT_JWT_SECRET,
        validation_alias="JWT_SECRET",
        description="HMAC signing key for access tokens",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
        description="One of HS256, HS384 or HS512",
    )
    access_token_minutes: int = Field(
        default=15,
        validation_alias="ACCESS_TOKEN_MINUTES",
        description="Access token lifetime in minutes",
    )
    cors_origins_raw: str = Field(
        default="http://localhost:5173",
        validation_alias="CORS_ORIGINS",
        description="Comma separated list of browser origins allowed to call the API",
    )
    frontend_origin_raw: str | None = Field(
        default=None,
        validation_alias=FRONTEND_ORIGIN_VARIABLE,
        description="The public address of the site, which the account messages link to",
    )
    revision: str = Field(
        default=LOCAL_REVISION,
        validation_alias="K_REVISION",
        description="The Cloud Run revision name, set by the platform and never by hand",
    )
    resend_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="RESEND_API_KEY",
        description="The Resend API key. Unset or the placeholder means email is off",
    )
    email_from: str = Field(
        default=DEFAULT_EMAIL_FROM,
        validation_alias="EMAIL_FROM",
        description="The From header of every email the service sends",
    )
    email_allowed_recipient: str | None = Field(
        default=None,
        validation_alias="EMAIL_ALLOWED_RECIPIENT",
        description="When set, the only address the service will send email to",
    )

    @field_validator("database_url")
    @classmethod
    def normalise_database_url(cls, value: str) -> str:
        """Force the psycopg driver so a bare postgres DSN cannot pick psycopg2."""
        return force_psycopg_driver(value)

    @field_validator("revision")
    @classmethod
    def default_blank_revision(cls, value: str) -> str:
        """Report a blank revision as the local one rather than as nothing."""
        return value.strip() or LOCAL_REVISION

    @field_validator("resend_api_key")
    @classmethod
    def treat_placeholder_key_as_unset(cls, value: SecretStr | None) -> SecretStr | None:
        """Read a blank key and the deployment placeholder as no key at all."""
        if value is None:
            return None
        candidate = value.get_secret_value().strip()
        if not candidate or candidate == RESEND_API_KEY_PLACEHOLDER:
            return None
        return SecretStr(candidate)

    @field_validator("email_from")
    @classmethod
    def default_blank_sender(cls, value: str) -> str:
        """Fall back to the default sender when the variable is set but blank."""
        return value.strip() or DEFAULT_EMAIL_FROM

    @field_validator("email_allowed_recipient")
    @classmethod
    def normalise_allowed_recipient(cls, value: str | None) -> str | None:
        """Lower case the one permitted recipient, and read a blank value as no restriction."""
        if value is None:
            return None
        return value.strip().lower() or None

    @field_validator("jwt_algorithm")
    @classmethod
    def check_algorithm(cls, value: str) -> str:
        """Reject any algorithm outside the supported HMAC set."""
        algorithm = value.strip().upper()
        if algorithm not in SUPPORTED_JWT_ALGORITHMS:
            raise ValueError(
                f"JWT_ALGORITHM must be one of {sorted(SUPPORTED_JWT_ALGORITHMS)}, got {value!r}."
            )
        return algorithm

    @field_validator("access_token_minutes")
    @classmethod
    def check_token_lifetime(cls, value: int) -> int:
        """Keep the access token lifetime inside a defensible window."""
        if not MINIMUM_ACCESS_TOKEN_MINUTES <= value <= MAXIMUM_ACCESS_TOKEN_MINUTES:
            raise ValueError(
                "ACCESS_TOKEN_MINUTES must be between "
                f"{MINIMUM_ACCESS_TOKEN_MINUTES} and {MAXIMUM_ACCESS_TOKEN_MINUTES}, got {value}."
            )
        return value

    @model_validator(mode="after")
    def forbid_placeholders_outside_development(self) -> Settings:
        """Fail when a deployed environment is still carrying development defaults."""
        if self.environment.is_relaxed:
            return self
        problems: list[str] = []
        if self.jwt_secret == DEVELOPMENT_JWT_SECRET:
            problems.append("JWT_SECRET is still the .env.example placeholder")
        if len(self.jwt_secret) < MINIMUM_JWT_SECRET_LENGTH:
            problems.append(
                f"JWT_SECRET is {len(self.jwt_secret)} characters, "
                f"the minimum is {MINIMUM_JWT_SECRET_LENGTH}"
            )
        if self.database_url == DEVELOPMENT_DATABASE_URL:
            problems.append("DATABASE_URL still points at the local development database")
        if problems:
            raise ValueError(
                f"Refusing to start in environment {self.environment.value!r}: "
                + "; ".join(problems)
                + ". Set the real values in the deployment environment."
            )
        return self

    @model_validator(mode="after")
    def keep_attempt_limits_within_bounds(self) -> Settings:
        """Refuse a limit under the floor, or one raised where the service is deployed."""
        check_attempt_limits(
            self.attempt_limits(),
            environment=self.environment.value,
            relaxed=self.environment.is_relaxed,
        )
        return self

    @model_validator(mode="after")
    def honour_the_test_clock_in_test_only(self) -> Settings:
        """Refuse to start any environment but test with its clock moved."""
        check_test_business_time(
            self.test_business_time,
            environment=self.environment.value,
            is_test=self.environment is Environment.TEST,
        )
        return self

    @model_validator(mode="after")
    def know_where_the_account_links_point(self) -> Settings:
        """Refuse to start when the origin of the account links cannot be worked out."""
        _ = self.frontend_origin
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Return the configured browser origins as a list."""
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def frontend_origin(self) -> str:
        """Return where the account links point, which is the one CORS origin when unset.

        Raises:
            ValueError: If there is no usable origin for this environment.

        """
        return resolve_frontend_origin(
            configured=self.frontend_origin_raw,
            cors_origins=self.cors_origins,
            environment=self.environment.value,
            relaxed=self.environment.is_relaxed,
        )

    @property
    def email_configured(self) -> bool:
        """Return True when there is an API key to send email with."""
        return self.resend_api_key is not None

    def redacted(self) -> dict[str, str | int | list[str]]:
        """Return the resolved configuration with every secret removed.

        Used by the startup log so an operator can confirm what the process
        actually loaded without the log becoming a credential leak.

        Three keys are named with care. The log redaction filter replaces the
        value of any key whose name contains `secret`, `token` or `api_key`,
        which would turn "set", the lifetime in minutes and the state of the
        email key into the placeholder and lose the facts this record exists
        to show. The one permitted recipient is an address, so the record says
        whether a restriction is on and not who it names. The attempt limits
        keep the names of their settings, which hold none of the three.
        """
        return {
            "environment": self.environment.value,
            "revision": self.revision,
            "database_host": _host_of(self.database_url),
            "jwt_algorithm": self.jwt_algorithm,
            "jwt_signing_key": "set" if self.jwt_secret else "missing",
            "access_lifetime_minutes": self.access_token_minutes,
            "cors_origins": self.cors_origins,
            "frontend_origin": self.frontend_origin,
            "email_delivery": "configured" if self.email_configured else "not-configured",
            "email_sender": self.email_from,
            "email_recipient_restriction": "on" if self.email_allowed_recipient else "off",
            "test_business_time": str(self.test_business_time or "off"),
            **self.attempt_limit_values(),
        }


def _host_of(database_url: str) -> str:
    """Extract the host and database name from a DSN, discarding credentials."""
    without_scheme = database_url.split("://", 1)[-1]
    return without_scheme.rsplit("@", 1)[-1] if "@" in without_scheme else without_scheme


def load_settings() -> Settings:
    """Build the settings object or fail with a message naming what is wrong.

    Raises:
        ConfigurationError: If a value is missing or fails a check. The
            original exception is deliberately not chained, because its text
            quotes the rejected values and a failed start is written to the
            log in full.

    """
    try:
        return Settings()
    except ValidationError as exc:
        aliases = (field.validation_alias for field in Settings.model_fields.values())
        variables = ", ".join(str(alias) for alias in aliases)
        raise ConfigurationError(
            "Failed to load backend configuration from the environment. "
            f"Attempted to read {variables}. Cause: {describe_failure(exc)}"
        ) from None


settings: Settings = load_settings()
