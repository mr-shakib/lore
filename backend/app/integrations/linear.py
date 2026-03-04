"""
Linear integration — POST /v1/webhooks/linear

Handles Linear webhook events:
  - Issue.update  → human updated an AI-generated issue title/description/priority

Security: Linear signs webhook payloads with HMAC-SHA256 via X-Linear-Signature.

OAuth setup: Linear → Settings → API → Webhooks → Add webhook → select Issue events.
"""

import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.database.postgres import get_connection
from app.models.events import CaptureEventCreate, CorrectionDelta, EventType, ToolName
from app.services.event_capture import EventCaptureService

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Signature verification ────────────────────────────────────────────────────

async def _verify_linear_signature(request: Request) -> bytes:
    if not settings.linear_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Linear integration not configured (missing LINEAR_WEBHOOK_SECRET).",
        )

    body = await request.body()
    signature = request.headers.get("X-Linear-Signature", "")

    expected = hmac.new(
        settings.linear_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid Linear signature.")

    return body


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("", summary="Receive Linear webhook payload")
async def linear_webhook(
    request: Request,
    conn: AsyncConnection = Depends(get_connection),
    _body: bytes = Depends(_verify_linear_signature),
    workspace_id: str | None = None,
) -> dict:
    payload = json.loads(_body)
    action = payload.get("action", "")

    if action == "update" and payload.get("type") == "Issue":
        await _handle_issue_update(payload, conn, workspace_id)

    return {"ok": True}


# ── Event handlers ────────────────────────────────────────────────────────────

async def _handle_issue_update(payload: dict, conn: AsyncConnection, workspace_id: str | None = None) -> None:
    """
    An issue was updated. We check if the update changes fields that are
    commonly set by AI (title, description, priority, assignee).
    Linear sends `updatedFrom` containing the previous values.
    """
    data = payload.get("data", {})
    updated_from = payload.get("updatedFrom", {})

    if not updated_from:
        return  # No change details — skip

    workspace_id = workspace_id or data.get("teamId", "unknown")
    actor_id = str(payload.get("actor", {}).get("id", "unknown"))

    # Build deltas for each changed field
    deltas: list[CorrectionDelta] = []
    ai_fields = {"title", "description", "priority", "assigneeId", "stateId"}

    for field, old_value in updated_from.items():
        if field in ai_fields:
            new_value = data.get(field)
            if new_value != old_value:
                deltas.append(
                    CorrectionDelta(
                        field=field,
                        change_type="content" if field in {"title", "description"} else "routing",
                        change_summary=f"Linear issue field '{field}' changed",
                    )
                )

    if not deltas:
        return

    capture = CaptureEventCreate(
        workspace_id=workspace_id,
        tool=ToolName.LINEAR,
        event_type=EventType.CORRECTION,
        actor_id=_hash_actor(workspace_id, actor_id),
        ai_output_id=f"linear:issue:{data.get('id', '')}",
        context_tags={
            "team_id": data.get("teamId", ""),
            "issue_id": data.get("id", ""),
            "priority": str(data.get("priority", "")),
        },
        delta=deltas,
        confidence_signal=0.80,
        external_ref=data.get("id"),
    )

    service = EventCaptureService(conn)
    await service.ingest(capture)
    logger.info(
        "linear_issue_update_captured",
        issue_id=data.get("id"),
        fields_changed=[d.field for d in deltas],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_actor(workspace_id: str, user_id: str) -> str:
    return hashlib.sha256(f"{workspace_id}:{user_id}".encode()).hexdigest()[:16]
