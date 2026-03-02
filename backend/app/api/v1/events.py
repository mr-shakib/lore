"""
Event Capture API — POST /v1/events

Entry point for all correction events. Used by:
  - The Lore SDK (custom AI agents)
  - Internal webhook adapters (Slack, GitHub, Linear)

Rate limiting: 1,000 events/minute per workspace (enforced via Redis).
Deduplication: events for the same actor+output within 5 minutes are collapsed.
"""

import hashlib
import json
import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.postgres import get_connection
from app.database.redis import (
    DEDUP_WINDOW_TTL,
    RATE_LIMIT_WINDOW,
    dedup_key,
    get_redis_dep,
    rate_limit_key,
)
from app.models.events import CaptureEvent, CaptureEventCreate, CaptureEventResponse
from app.services.event_capture import EventCaptureService

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _check_rate_limit(workspace_id: str, redis: Redis) -> None:
    """Sliding window rate limiter. Raises 429 if limit exceeded."""
    from app.config import settings

    key = rate_limit_key(workspace_id, "events")
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, RATE_LIMIT_WINDOW)

    if count > settings.event_rate_limit_per_workspace:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Workspace exceeded {settings.event_rate_limit_per_workspace} events/minute.",
                "retry_after_seconds": RATE_LIMIT_WINDOW,
            },
        )


async def _check_dedup(event: CaptureEventCreate, redis: Redis) -> bool:
    """
    Returns True if this event is a duplicate (same actor + output within 5 min).
    Uses Redis SET NX (set if not exists) as an atomic check-and-set.
    """
    if not event.ai_output_id:
        return False  # Cannot dedup without an output reference

    key = dedup_key(event.workspace_id, event.actor_id, event.ai_output_id)
    # SET key 1 NX EX ttl — returns True if key was newly set, False if it already existed
    is_new = await redis.set(key, "1", nx=True, ex=DEDUP_WINDOW_TTL)
    return not bool(is_new)  # is_new=None means key existed (duplicate)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CaptureEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a correction event",
    description=(
        "Accepts a structured correction event from the Lore SDK or a webhook adapter. "
        "Events are rate-limited (1,000/min per workspace) and deduplicated "
        "(same actor+output within 5 min collapses to one event). "
        "Returns 202 Accepted — processing happens asynchronously."
    ),
)
async def ingest_event(
    payload: CaptureEventCreate,
    conn: AsyncConnection = Depends(get_connection),
    redis: Redis = Depends(get_redis_dep),
) -> CaptureEventResponse:
    t_start = time.perf_counter()

    # 1. Rate limit
    await _check_rate_limit(payload.workspace_id, redis)

    # 2. Deduplication
    if await _check_dedup(payload, redis):
        logger.info(
            "event_deduplicated",
            workspace_id=payload.workspace_id,
            actor_id=payload.actor_id,
            ai_output_id=payload.ai_output_id,
        )
        return CaptureEventResponse(
            event_id="deduplication",
            status="deduplicated",
            message="Duplicate event within 5-minute deduplication window — ignored.",
        )

    # 3. Persist + queue
    service = EventCaptureService(conn)
    event = await service.ingest(payload)

    latency_ms = int((time.perf_counter() - t_start) * 1000)
    logger.info(
        "event_ingested",
        event_id=event.event_id,
        workspace_id=event.workspace_id,
        tool=event.tool,
        event_type=event.event_type,
        latency_ms=latency_ms,
    )

    return CaptureEventResponse(event_id=event.event_id)


@router.get(
    "/{event_id}",
    response_model=CaptureEvent,
    summary="Get a single event by ID",
)
async def get_event(
    event_id: str,
    conn: AsyncConnection = Depends(get_connection),
) -> CaptureEvent:
    service = EventCaptureService(conn)
    event = await service.get_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found.")
    return event


@router.get(
    "",
    summary="List events for a workspace (paginated)",
)
async def list_events(
    workspace_id: str,
    page: int = 1,
    page_size: int = 50,
    conn: AsyncConnection = Depends(get_connection),
) -> dict:
    service = EventCaptureService(conn)
    items, total = await service.list_events(workspace_id, page=page, page_size=page_size)
    return {
        "items": [e.model_dump() for e in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
