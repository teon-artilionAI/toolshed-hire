"""Router assembly.

Every router is mounted under a single `/api` prefix, which is the path Vercel
rewrites to Cloud Run. The browser therefore sees one origin, no preflight is
issued, and the refresh cookie stays same site.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    allocations,
    auth,
    availability,
    branches,
    catalogue,
    health,
    me,
    quote,
)

API_PREFIX = "/api"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(allocations.router)
api_router.include_router(branches.router)
api_router.include_router(catalogue.router)
api_router.include_router(availability.router)
api_router.include_router(quote.router)

__all__ = ["API_PREFIX", "api_router"]
