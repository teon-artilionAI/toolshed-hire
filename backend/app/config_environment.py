"""The environment a process runs in, and the error of a configuration it cannot use.

These two are stated apart from the settings so that `config.py` stays a list
of settings. `config.py` exports both under their own names, so everything
that imports them from there carries on working.
"""

from __future__ import annotations

from enum import Enum


class Environment(str, Enum):
    """The deployment environment the process believes it is running in."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_relaxed(self) -> bool:
        """Return True when placeholder secrets are tolerated.

        This is the one question every start-up check asks. Staging answers it
        the same way production does, so a check written against it cannot
        treat the two differently by accident.
        """
        return self in (Environment.DEVELOPMENT, Environment.TEST)


class ConfigurationError(RuntimeError):
    """Raised when the environment cannot produce a usable configuration."""
