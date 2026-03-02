"""
Lore FastAPI application — entry point.

Startup sequence:
  1. Init PostgreSQL connection pool (asyncpg via SQLAlchemy)
  2. Init Neo4j driver
  3. Init Redis client
  4. Start Kafka producer (event pipeline)
  5. Mount API routers

Shutdown: all connections closed gracefully via lifespan context manager.
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.postgres import close_db, init_db
from app.database.redis import close_redis, init_redis
from app.workers.pattern_mining_worker import start_scheduler, stop_scheduler

logger = structlog.get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup / shutdown of all external connections."""
    logger.info(
        "lore_api_starting",
        version=settings.app_version,
        environment=settings.environment,
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────
    try:
        await init_db()
    except Exception as exc:
        logger.error("postgres_init_failed", error=str(exc))
        raise  # fatal — API cannot serve requests without DB

    # ── Redis ─────────────────────────────────────────────────────────────
    try:
        await init_redis()
    except Exception as exc:
        # Non-fatal: caching degrades gracefully, requests still work
        logger.warning("redis_init_failed", error=str(exc))

    # ── Background scheduler ──────────────────────────────────────────────
    try:
        start_scheduler()
    except Exception as exc:
        # Non-fatal: mining runs manually via POST /v1/mining/run
        logger.warning("scheduler_init_failed", error=str(exc))

    logger.info("lore_api_ready")
    yield

    try:
        stop_scheduler()
    except Exception:
        pass
    await close_db()
    await close_redis()

    logger.info("lore_api_shutdown")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "The organizational memory layer for AI-native companies. "
            "Captures AI corrections, builds a Company Context Graph, and injects "
            "context back into every future AI call."
        ),
        # Docs visible unless explicitly disabled (DOCS_ENABLED=false)
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    origins = (
        ["*"]
        if settings.debug
        else [
            "https://app.lore.dev",
            "https://lore.dev",
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request timing middleware ─────────────────────────────────────────────
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        return response

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.api.v1 import router as v1_router  # imported here to avoid circular deps
    app.include_router(v1_router, prefix="/v1")

    # ── Root ─────────────────────────────────────────────────────────────────
    @app.get("/", tags=["meta"], summary="API root")
    async def root() -> dict:
        return {
            "product": "Lore",
            "version": settings.app_version,
            "status": "operational",
            "docs": "/docs",
        }

    return app


app = create_app()
