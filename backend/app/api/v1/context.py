"""
Context Injection API — POST /v1/context

The core product endpoint. Every connected AI agent calls this before
generating output. Lore assembles relevant organizational context from the
Company Context Graph and returns it as a formatted prompt injection.

SLA targets:
  p50: < 80ms
  p95: < 200ms
  p99: < 500ms

Cache: identical requests within 15 minutes are served from Redis.
Fallback: if Lore is unavailable, the SDK returns empty context and logs the miss.
"""

import hashlib
import json
import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.database.postgres import get_connection
from app.database.redis import (
    CONTEXT_CACHE_TTL,
    context_cache_key,
    get_redis_dep,
)
from app.models.context import ContextRequest, ContextResponse
from app.services.context_graph import ContextGraphService

logger = structlog.get_logger(__name__)
router = APIRouter()


def _request_hash(req: ContextRequest) -> str:
    """Stable hash of a context request for cache keying."""
    payload = json.dumps(
        {
            "tool": req.tool,
            "task": req.task,
            "entities": sorted(req.entities),
            "context_tags": dict(sorted(req.context_tags.items())),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@router.post(
    "",
    response_model=ContextResponse,
    summary="Fetch organizational context for an AI agent",
    description=(
        "The primary Lore endpoint. Call this before every LLM invocation. "
        "Returns active rules, entity facts, and relevant decisions from the "
        "Company Context Graph as a structured prompt injection block.\n\n"
        "**Caching:** Identical requests within 15 minutes are served from Redis cache.\n"
        "**Fallback:** Returns an empty context object (never raises 5xx) so your AI tool "
        "continues working even if Lore is temporarily unreachable."
    ),
)
async def get_context(
    request: ContextRequest,
    workspace_id: str,
    redis: Redis = Depends(get_redis_dep),
    conn=Depends(get_connection),
) -> ContextResponse:
    t_start = time.perf_counter()

    # ── Cache check ───────────────────────────────────────────────────────────
    cache_key = context_cache_key(workspace_id, request.tool, _request_hash(request))
    cached = await redis.get(cache_key)
    if cached:
        response = ContextResponse.model_validate_json(cached)
        response.cache_hit = True
        response.latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.info(
            "context_cache_hit",
            workspace_id=workspace_id,
            tool=request.tool,
            latency_ms=response.latency_ms,
        )
        return response

    # ── Assemble from graph ───────────────────────────────────────────────────
    service = ContextGraphService(conn)
    response = await service.assemble_context(workspace_id, request)
    response.latency_ms = int((time.perf_counter() - t_start) * 1000)

    # ── Cache the result ──────────────────────────────────────────────────────
    await redis.set(cache_key, response.model_dump_json(), ex=CONTEXT_CACHE_TTL)

    logger.info(
        "context_assembled",
        workspace_id=workspace_id,
        tool=request.tool,
        rules_count=len(response.rules),
        entities_count=len(response.entities),
        latency_ms=response.latency_ms,
    )

    return response
