"""The longer checks `config.py` applies, as plain functions over plain values.

`config.py` declares the settings and says which check each one gets. The
checks that take more than a line or two live here, so that file stays a list
of settings and each rule can be read by itself.

Every check raises `ValueError` with a message that names the environment
variable it is about. A message never repeats a value that could hold a
credential. An attempt limit is a small number and is quoted. A connection
string is not, and only its scheme is.

Every attempt limit gets two checks (C-17). None may be below one. A limit of
zero is a rule that lets nobody through, and the throttle refuses to build
one. I set the floor no higher than that, because a limit far below the
default is what an operator may want while an attack is running, and it is not
for the start-up check to overrule them. Outside development and test no limit
may be above its default either. The defaults of the two sign in limits are
the ones the design document sets, and the others are mine, so a deployed
service can be made stricter than the design and never looser. Development and
test accept any limit from the floor up, which is what lets a browser test run
sign one seeded account in more often than a person would.

The frontend origin is where the links in the account messages point. Left
unset it is the one origin in `CORS_ORIGINS`, which in a deployment is the
site itself. A deployed service refuses an origin that is not `https`, or
that is this machine, because a link to either would be of no use to the
person who received it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from pydantic import ValidationError

REQUIRED_DRIVER_PREFIX: Final[str] = "postgresql+psycopg://"
BARE_POSTGRES_PREFIXES: Final[tuple[str, ...]] = ("postgres://", "postgresql://")

# The lowest limit a throttle rule can have and still let anybody through.
MINIMUM_LOGIN_ATTEMPTS: Final[int] = 1

FRONTEND_ORIGIN_VARIABLE: Final[str] = "FRONTEND_ORIGIN"
DEVELOPMENT_FRONTEND_ORIGIN: Final[str] = "http://localhost:5173"
SECURE_SCHEME: Final[str] = "https"
ORIGIN_SCHEMES: Final[frozenset[str]] = frozenset({"http", SECURE_SCHEME})
LOCAL_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})
PATH_SEPARATOR: Final[str] = "/"


@dataclass(frozen=True, slots=True)
class AttemptLimit:
    """One throttle limit as it was configured.

    Attributes:
        variable: The environment variable the limit is read from.
        value: The configured limit.
        default: The limit when the variable is unset.

    """

    variable: str
    value: int
    default: int


def force_psycopg_driver(value: str) -> str:
    """Return a PostgreSQL DSN on the psycopg driver, so a bare one cannot pick psycopg2.

    Raises:
        ValueError: If the value is blank or is not a PostgreSQL DSN.

    """
    candidate = value.strip()
    if not candidate:
        raise ValueError("DATABASE_URL was empty. Set it to a PostgreSQL DSN.")
    for prefix in BARE_POSTGRES_PREFIXES:
        if candidate.startswith(prefix):
            return REQUIRED_DRIVER_PREFIX + candidate[len(prefix) :]
    if not candidate.startswith(REQUIRED_DRIVER_PREFIX):
        # Only the scheme is repeated. The rest of the value holds the
        # credentials, and this message ends up in the start-up log.
        scheme, separator, _rest = candidate.partition("://")
        found = f"the scheme {scheme!r}" if separator else "a value with no scheme"
        raise ValueError(
            "DATABASE_URL must be a PostgreSQL DSN. Expected a value starting with "
            f"{REQUIRED_DRIVER_PREFIX!r}, postgres:// or postgresql://, got {found}."
        )
    return candidate


def _limit_problem(limit: AttemptLimit, environment: str, relaxed: bool) -> str | None:
    """Return what is wrong with one attempt limit, or None when it may be used."""
    if limit.value < MINIMUM_LOGIN_ATTEMPTS:
        return f"{limit.variable} must be at least {MINIMUM_LOGIN_ATTEMPTS}, got {limit.value}."
    if not relaxed and limit.value > limit.default:
        return (
            f"{limit.variable} must not be above its default of {limit.default} in environment "
            f"{environment!r}, got {limit.value}. Outside development and test a limit can be "
            "lowered and never raised."
        )
    return None


def check_attempt_limits(
    limits: Iterable[AttemptLimit], *, environment: str, relaxed: bool
) -> None:
    """Refuse a limit under the floor, or one raised where the service is deployed.

    Every limit is checked before anything is raised, so one failed start
    names everything that has to be put right.

    Args:
        limits: Each configured limit with its variable and its default.
        environment: The name of the environment, for the message.
        relaxed: True in development and test, where a limit may be raised.

    Raises:
        ValueError: If any limit is below the floor, or is above its default
            while `relaxed` is False.

    """
    problems = [
        problem for limit in limits if (problem := _limit_problem(limit, environment, relaxed))
    ]
    if problems:
        raise ValueError(" ".join(problems))


def resolve_frontend_origin(
    *, configured: str | None, cors_origins: Sequence[str], environment: str, relaxed: bool
) -> str:
    """Return the origin the links in the account messages point at.

    Args:
        configured: The value of `FRONTEND_ORIGIN`, or None when it is unset.
        cors_origins: The origins of `CORS_ORIGINS`. When `FRONTEND_ORIGIN`
            is unset and this holds exactly one, that one is used.
        environment: The name of the environment, for the message.
        relaxed: True in development and test, where the Vite dev server is
            an acceptable answer.

    Returns:
        The origin with no trailing slash, for example `https://www.example.co.za`.

    Raises:
        ValueError: If no origin can be worked out, if the value is not an
            origin, or if a deployed environment is given one that is not
            `https` or that names this machine.

    """
    candidate = (configured or "").strip()
    if not candidate and len(cors_origins) == 1:
        candidate = cors_origins[0]
    if not candidate and relaxed:
        candidate = DEVELOPMENT_FRONTEND_ORIGIN
    if not candidate:
        raise ValueError(
            f"{FRONTEND_ORIGIN_VARIABLE} is not set and CORS_ORIGINS holds {len(cors_origins)} "
            "origins, so there is no telling where the links in the account messages should "
            f"point. Set {FRONTEND_ORIGIN_VARIABLE} to the public address of the site."
        )
    origin = candidate.rstrip(PATH_SEPARATOR)
    parts = urlsplit(origin)
    has_more_than_an_origin = bool(parts.path or parts.query or parts.fragment)
    if parts.scheme not in ORIGIN_SCHEMES or not parts.hostname or has_more_than_an_origin:
        raise ValueError(
            f"{FRONTEND_ORIGIN_VARIABLE} must be an origin such as https://www.example.co.za, "
            "which is a scheme and a host with no path."
        )
    if not relaxed and (parts.scheme != SECURE_SCHEME or parts.hostname in LOCAL_HOSTS):
        raise ValueError(
            f"{FRONTEND_ORIGIN_VARIABLE} must be the public https address of the site in "
            f"environment {environment!r}. Set it, or set CORS_ORIGINS to that one address."
        )
    return origin


def describe_failure(failure: ValidationError) -> str:
    """Say what each failed check said, without the value that failed it.

    The text pydantic renders for a failure quotes the input it rejected, and
    here the input is the signing key and the connection string. So the
    message is rebuilt from the name of each setting and the reason alone.
    """
    reasons = failure.errors(include_url=False, include_context=False, include_input=False)
    return "; ".join(
        f"{'.'.join(str(part) for part in reason['loc']) or 'settings'}: {reason['msg']}"
        for reason in reasons
    )
