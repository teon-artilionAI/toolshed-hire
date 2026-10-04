"""Router assembly.

Every router is mounted under a single `/api` prefix, which is the path Vercel
rewrites to Cloud Run. The browser therefore sees one origin, no preflight is
issued, and the refresh cookie stays same site.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import (
    account,
    admin_audit,
    admin_categories,
    admin_corrections,
    admin_models,
    admin_notifications,
    admin_reports,
    assets,
    auth,
    availability,
    branches,
    catalogue,
    checkout,
    counter,
    customers,
    damage_reports,
    health,
    me,
    my_rentals,
    profile,
    quote,
    rentals,
    reservation_reads,
    reservations,
)

API_PREFIX = "/api"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(me.router)
api_router.include_router(profile.router)
api_router.include_router(my_rentals.router)
api_router.include_router(customers.router)
api_router.include_router(reservations.router)
api_router.include_router(reservation_reads.router)
api_router.include_router(checkout.router)
api_router.include_router(rentals.router)
api_router.include_router(damage_reports.router)
api_router.include_router(counter.router)
api_router.include_router(assets.router)
api_router.include_router(admin_reports.router)
api_router.include_router(admin_audit.router)
api_router.include_router(admin_notifications.router)
api_router.include_router(admin_corrections.router)
api_router.include_router(admin_categories.router)
api_router.include_router(admin_models.router)
api_router.include_router(branches.router)
api_router.include_router(catalogue.router)
api_router.include_router(availability.router)
api_router.include_router(quote.router)

__all__ = ["API_PREFIX", "api_router"]
