"""API v1 — mounts all route modules under /v1."""

from fastapi import APIRouter

from app.api.v1.context import router as context_router
from app.api.v1.entities import router as entities_router
from app.api.v1.events import router as events_router
from app.api.v1.health import router as health_router
from app.api.v1.rules import router as rules_router
from app.api.v1.webhooks import router as webhooks_router

router = APIRouter()

router.include_router(health_router, tags=["health"])
router.include_router(events_router, prefix="/events", tags=["events"])
router.include_router(context_router, prefix="/context", tags=["context"])
router.include_router(rules_router, prefix="/rules", tags=["rules"])
router.include_router(entities_router, prefix="/entities", tags=["entities"])
router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
