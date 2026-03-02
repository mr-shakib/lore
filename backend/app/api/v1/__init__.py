"""API v1 — mounts all route modules under /v1."""

from fastapi import APIRouter, Depends

from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.bootstrap import router as bootstrap_router
from app.api.v1.context import router as context_router
from app.api.v1.entities import router as entities_router
from app.api.v1.events import router as events_router
from app.api.v1.health import router as health_router
from app.api.v1.mining import router as mining_router
from app.api.v1.proposals import router as proposals_router
from app.api.v1.rules import router as rules_router
from app.api.v1.webhooks import router as webhooks_router
from app.middleware.auth import require_auth

# Dependency applied to every protected router.
# /health and /webhooks intentionally excluded — they must stay open.
_auth = [Depends(require_auth)]

router = APIRouter()

# ── Open routes (no auth) ─────────────────────────────────────────────────────
router.include_router(health_router,    tags=["health"])
router.include_router(webhooks_router,  prefix="/webhooks",     tags=["webhooks"])
router.include_router(bootstrap_router, prefix="/auth/bootstrap", tags=["auth"])

# ── Protected routes (require auth) ──────────────────────────────────────────
router.include_router(events_router,    prefix="/events",    tags=["events"],    dependencies=_auth)
router.include_router(context_router,   prefix="/context",   tags=["context"],   dependencies=_auth)
router.include_router(rules_router,     prefix="/rules",     tags=["rules"],     dependencies=_auth)
router.include_router(proposals_router, prefix="/proposals", tags=["proposals"], dependencies=_auth)
router.include_router(entities_router,  prefix="/entities",  tags=["entities"],  dependencies=_auth)
router.include_router(mining_router,    prefix="/mining",    tags=["mining"],    dependencies=_auth)
router.include_router(api_keys_router,  prefix="/auth/api-keys", tags=["auth"],  dependencies=_auth)
