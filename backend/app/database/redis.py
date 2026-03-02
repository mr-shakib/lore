"""
Redis connection via redis-py async client (Upstash Redis compatible).

Used for:
  - Context injection response cache (15-minute TTL)
  - Workspace-level rate limiting counters
  - Session state for SDK auth
  - Deduplication window tracking (5-minute event dedup)
"""

from typing import AsyncGenerator

import structlog
from redis.asyncio import Redis, from_url

from app.config import settings

logger = structlog.get_logger(__name__)

_redis: Redis | None = None


# ── Startup / shutdown ────────────────────────────────────────────────────────

async def init_redis() -> None:
    """Create Redis async client and verify connectivity."""
    global _redis

    # Upstash Redis uses rediss:// (TLS). ssl_cert_reqs=None disables cert
    # verification, which is required for Upstash's managed TLS certificates.
    kwargs: dict = {"encoding": "utf-8", "decode_responses": True}
    if settings.redis_url.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = None

    _redis = from_url(settings.redis_url, **kwargs)

    # Smoke test
    await _redis.ping()
    logger.info("redis_connected", url=_redact(settings.redis_url))


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("redis_disconnected")


# ── Accessor ──────────────────────────────────────────────────────────────────

def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _redis


async def get_redis_dep() -> AsyncGenerator[Redis, None]:
    """
    FastAPI dependency — yields the shared Redis client.

    Usage::

        @router.get("/cached-example")
        async def example(redis: Redis = Depends(get_redis_dep)):
            value = await redis.get("some-key")
    """
    yield get_redis()


# ── Cache helpers ─────────────────────────────────────────────────────────────

CONTEXT_CACHE_TTL = 15 * 60       # 15 minutes (seconds)
DEDUP_WINDOW_TTL = 5 * 60         # 5 minutes
RATE_LIMIT_WINDOW = 60            # 1 minute


def context_cache_key(workspace_id: str, tool: str, task_hash: str) -> str:
    return f"lore:ctx:{workspace_id}:{tool}:{task_hash}"


def dedup_key(workspace_id: str, actor_id: str, output_id: str) -> str:
    return f"lore:dedup:{workspace_id}:{actor_id}:{output_id}"


def rate_limit_key(workspace_id: str, bucket: str) -> str:
    return f"lore:rl:{workspace_id}:{bucket}"


def _redact(url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        redacted = parsed._replace(netloc=f"***@{parsed.hostname}:{parsed.port}")
        return urlunparse(redacted)
    except Exception:
        return "***"
