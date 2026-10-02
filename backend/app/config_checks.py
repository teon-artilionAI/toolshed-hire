"""The longer checks `config.py` applies, as plain functions over plain values.

`config.py` declares the settings and says which check each one gets. The
checks that take more than a line or two live here, so that file stays a list
of settings and each rule can be read by itself.

Every check raises `ValueError` with a message that names the environment
variable it is about. A message never repeats a value that could hold a
credential. A sign in limit is a small number and is quoted. A connection
string is not, and only its scheme is.

The two sign in limits get two checks (C-17). Neither may be below one. A
limit of zero is a rule that lets nobody sign in, and the throttle refuses to
build one. I set the floor no higher than that, because a limit far below the
default is what an operator may want while an attack is running, and it is not
for the start-up check to overrule them. Outside development and test neither
limit may be above its default either. The defaults are the limits the design
document sets, so a deployed service can be made stricter than the design and
never looser. Development and test accept any limit from the floor up, which
is what lets a browser test run sign one seeded account in more often than a
person would.
"""

from __future__ import annotations

from typing import Final

from pydantic import ValidationError

from app.application.identity.sign_in import LOGIN_ATTEMPTS_PER_ADDRESS, LOGIN_ATTEMPTS_PER_EMAIL

REQUIRED_DRIVER_PREFIX: Final[str] = "postgresql+psycopg://"
BARE_POSTGRES_PREFIXES: Final[tuple[str, ...]] = ("postgres://", "postgresql://")

LOGIN_ATTEMPTS_PER_EMAIL_VARIABLE: Final[str] = "LOGIN_ATTEMPTS_PER_EMAIL"
LOGIN_ATTEMPTS_PER_ADDRESS_VARIABLE: Final[str] = "LOGIN_ATTEMPTS_PER_ADDRESS"
# The lowest limit a sign in rule can have and still let anybody in.
MINIMUM_LOGIN_ATTEMPTS: Final[int] = 1


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


def _login_limit_problem(
    variable: str, value: int, default: int, environment: str, relaxed: bool
) -> str | None:
    """Return what is wrong with one sign in limit, or None when it may be used."""
    if value < MINIMUM_LOGIN_ATTEMPTS:
        return f"{variable} must be at least {MINIMUM_LOGIN_ATTEMPTS}, got {value}."
    if not relaxed and value > default:
        return (
            f"{variable} must not be above its default of {default} in environment "
            f"{environment!r}, got {value}. Outside development and test a sign in limit "
            "can be lowered and never raised."
        )
    return None


def check_login_limits(
    *, per_email: int, per_address: int, environment: str, relaxed: bool
) -> None:
    """Refuse a sign in limit under the floor, or one raised where the service is deployed.

    Both limits are checked before anything is raised, so one failed start
    names everything that has to be put right.

    Args:
        per_email: The configured attempts one email address may make in a window.
        per_address: The configured attempts one client address may make in a window.
        environment: The name of the environment, for the message.
        relaxed: True in development and test, where a limit may be raised.

    Raises:
        ValueError: If either limit is below the floor, or is above its
            default while `relaxed` is False.

    """
    limits = (
        (LOGIN_ATTEMPTS_PER_EMAIL_VARIABLE, per_email, LOGIN_ATTEMPTS_PER_EMAIL),
        (LOGIN_ATTEMPTS_PER_ADDRESS_VARIABLE, per_address, LOGIN_ATTEMPTS_PER_ADDRESS),
    )
    problems = [
        problem
        for variable, value, default in limits
        if (problem := _login_limit_problem(variable, value, default, environment, relaxed))
    ]
    if problems:
        raise ValueError(" ".join(problems))


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
