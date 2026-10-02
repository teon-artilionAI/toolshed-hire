"""Deny by default, checked against the route table (C-20, C-21, BR-41).

Every route says who may call it. It says so by depending on a policy
dependency, which is one of three kinds.

`public_access` in `app/api/deps.py` admits a caller with no account. A
dependency built by `require_roles` admits the roles it names. The refresh
cookie dependency in `app/api/identity_deps.py` admits whoever holds a refresh
cookie. Each of them is registered here with `declare_policy` when it is
defined, and that registration is the declaration.

`enforce_declared_policies` walks the route table of an application and reads
the policy of every route back out of its dependency tree. A route with no
registered dependency anywhere in that tree has declared nothing, and the
application refuses to start with a message that names it. A route that
declares itself public and names roles as well has contradicted itself and is
refused the same way.

The walk covers everything the application serves. A route that is not an API
route, a mounted static directory for example, has no dependency tree to read,
so it is refused unless its path is in the short list the caller passes in.
The application factory passes the paths of the interactive documentation,
which exist in development and test only.

The same walk is exposed as `declared_routes`, so a test can enumerate the
table and fail a build before a missing policy can fail a deployment.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Final

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from app.domain.enums import UserRole

logger = logging.getLogger(__name__)

METHOD_SEPARATOR: Final[str] = ","
# Starlette adds HEAD to every GET route. It is the same route and the same
# policy, so it is left out of the name a route is reported under.
IMPLIED_METHODS: Final[frozenset[str]] = frozenset({"HEAD"})
UNKNOWN_PATH: Final[str] = "<a route with no path>"


class AccessKind(str, Enum):
    """The three ways a route can say who may call it."""

    PUBLIC = "public"
    ROLES = "roles"
    REFRESH_COOKIE = "refresh-cookie"


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """Who a policy dependency admits.

    Attributes:
        kind: Which of the three kinds of policy this is.
        roles: The roles admitted, for a policy of the `ROLES` kind.

    """

    kind: AccessKind
    roles: frozenset[UserRole] = frozenset()


PUBLIC_POLICY: Final[AccessPolicy] = AccessPolicy(kind=AccessKind.PUBLIC)
REFRESH_COOKIE_POLICY: Final[AccessPolicy] = AccessPolicy(kind=AccessKind.REFRESH_COOKIE)

# Every policy dependency, with what it admits. A dependency lives as long as
# the module that defined it, so nothing is ever removed. The key is typed as
# an object because a dependency may be a function of any signature.
_declared: dict[object, AccessPolicy] = {}


def declare_policy(dependency: object, policy: AccessPolicy) -> None:
    """Register a dependency as one that declares who may call a route.

    Args:
        dependency: The function a route depends on, exactly as it is handed
            to `Depends`.
        policy: Who that dependency admits.

    """
    _declared[dependency] = policy


def role_policy(roles: frozenset[UserRole]) -> AccessPolicy:
    """Return the policy that admits exactly the given roles."""
    return AccessPolicy(kind=AccessKind.ROLES, roles=roles)


@dataclass(frozen=True, slots=True)
class DeclaredRoute:
    """One route of an application and the policies found in its dependency tree.

    Attributes:
        name: The methods and the full path template, for example
            `POST /api/auth/login`.
        path: The full path template alone.
        policies: Every distinct policy the route depends on. Empty when the
            route declared nothing.

    """

    name: str
    path: str
    policies: frozenset[AccessPolicy]


class UndeclaredPolicyError(RuntimeError):
    """Raised at start-up when a route does not say who may call it."""


def declared_routes(
    application: FastAPI, *, framework_paths: frozenset[str] = frozenset()
) -> list[DeclaredRoute]:
    """Return every route the application serves, with the policies it declares.

    Args:
        application: The application whose route table is read.
        framework_paths: Exact paths served by the framework itself, which
            carry no dependency tree. Each is reported as public.

    """
    found: list[DeclaredRoute] = []
    for context in iter_route_contexts(application.routes):
        path = context.path_format or context.path or UNKNOWN_PATH
        methods = sorted((context.methods or set()) - IMPLIED_METHODS)
        name = f"{METHOD_SEPARATOR.join(methods)} {path}".strip()
        if isinstance(context.original_route, APIRoute):
            dependant: Dependant | None = context.dependant
            policies = frozenset(_policies_in(dependant)) if dependant is not None else frozenset()
        elif path in framework_paths:
            policies = frozenset({PUBLIC_POLICY})
        else:
            policies = frozenset()
        found.append(DeclaredRoute(name=name, path=path, policies=policies))
    return found


def enforce_declared_policies(
    application: FastAPI, *, framework_paths: frozenset[str] = frozenset()
) -> None:
    """Refuse an application in which any route has not declared who may call it.

    Args:
        application: The application about to be served.
        framework_paths: Exact paths served by the framework itself.

    Raises:
        UndeclaredPolicyError: If a route declares no policy, or declares that
            it is public and that it admits roles. The message names each one.

    """
    routes = declared_routes(application, framework_paths=framework_paths)
    undeclared = sorted(route.name for route in routes if not route.policies)
    contradictory = sorted(route.name for route in routes if _contradicts_itself(route))
    if undeclared or contradictory:
        logger.error(
            "startup.route_policy_missing",
            extra={"undeclared_routes": undeclared, "contradictory_routes": contradictory},
        )
        raise UndeclaredPolicyError(
            "Refusing to start. Every route must declare who may call it (BR-41). "
            f"Routes with no declared policy: {undeclared or 'none'}. Routes that declare "
            f"themselves public and name roles as well: {contradictory or 'none'}. Give each "
            "route a role dependency from app/api/deps.py, or `public_access` when it admits "
            "a caller with no account."
        )
    logger.info("startup.route_policies_declared", extra={"route_count": len(routes)})


def _policies_in(dependant: Dependant) -> Iterator[AccessPolicy]:
    """Yield the policy of every registered dependency in a dependency tree."""
    if dependant.call is not None and dependant.call in _declared:
        yield _declared[dependant.call]
    for child in dependant.dependencies:
        yield from _policies_in(child)


def _contradicts_itself(route: DeclaredRoute) -> bool:
    """Return True when a route is declared public and protected at once."""
    kinds = {policy.kind for policy in route.policies}
    return AccessKind.PUBLIC in kinds and len(kinds) > 1
