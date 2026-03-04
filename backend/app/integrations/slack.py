"""
Slack integration — POST /v1/webhooks/slack

Handles Slack Events API payloads:
  - message.changed  → human edited a bot/AI message → correction event
  - reaction_added   → special reactions (❌ 👎) on AI messages → rejection event

Security: Slack signs every request with HMAC-SHA256.
We verify the X-Slack-Signature header before processing any payload.

Permissions required in the Slack App:
  - channels:history
  - reactions:read
  - No write permissions
"""

import hashlib
import hmac
import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.database.postgres import get_connection
from app.models.events import CaptureEventCreate, CorrectionDelta, EventType, ToolName
from app.services.event_capture import EventCaptureService

logger = structlog.get_logger(__name__)
router = APIRouter()

# Reactions that signal AI output rejection
REJECTION_REACTIONS = {"x", "-1", "thumbsdown", "no_entry", "no_entry_sign"}


# ── Signature verification ────────────────────────────────────────────────────

async def _verify_slack_signature(request: Request) -> bytes:
    """
    Verifies the X-Slack-Signature header using HMAC-SHA256.
    Raises 403 if invalid or if the signing secret is not configured.
    NOTE: Do not use this as a Depends on url_verification — Slack's challenge
    request has no signature. Call _verify_slack_signature_body instead, after
    handling url_verification.
    """
    body = await request.body()
    await _verify_slack_signature_body(request, body)
    return body


async def _verify_slack_signature_body(request: Request, body: bytes) -> None:
    """
    Inner HMAC verification — call this after reading the body yourself,
    so url_verification can be handled before this check runs.
    """
    if not settings.slack_signing_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack integration not configured (missing SLACK_SIGNING_SECRET).",
        )

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    # Reject replayed requests older than 5 minutes
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise HTTPException(status_code=403, detail="Request timestamp too old (replay protection).")
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid timestamp.")

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    expected = (
        "v0="
        + hmac.new(
            settings.slack_signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature.")


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("", summary="Receive Slack Events API payload")
async def slack_webhook(
    request: Request,
    conn: AsyncConnection = Depends(get_connection),
    workspace_id: str | None = None,
) -> dict:
    import json

    body = await request.body()
    payload = json.loads(body)

    # Slack URL verification challenge — must respond BEFORE signature check.
    # Slack sends this once when you first configure the webhook URL.
    # It has no X-Slack-Signature header, so we respond immediately.
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # All other events must pass signature verification
    await _verify_slack_signature_body(request, body)

    event = payload.get("event", {})
    event_type = event.get("type", "")

    if event_type == "message" and event.get("subtype") == "message_changed":
        await _handle_message_changed(event, conn, workspace_id)

    elif event_type == "reaction_added":
        if event.get("reaction") in REJECTION_REACTIONS:
            await _handle_rejection_reaction(event, conn, workspace_id)

    return {"ok": True}


# ── Event handlers ────────────────────────────────────────────────────────────

async def _handle_message_changed(event: dict, conn: AsyncConnection, workspace_id: str | None = None) -> None:
    """
    A message was edited. If the previous message was from a bot/AI and
    the editor is a human, this is a correction event.
    """
    message = event.get("message", {})
    previous = event.get("previous_message", {})

    # Only capture if original was from a bot
    if previous.get("subtype") != "bot_message" and not previous.get("bot_id"):
        return

    actor_id = message.get("user", "unknown")
    if not actor_id or actor_id == previous.get("bot_id"):
        return  # Bot edited its own message — not a correction

    workspace_id = workspace_id or event.get("authed_users", ["unknown"])[0]
    channel = event.get("channel", "unknown")
    ts = event.get("ts", "")

    capture = CaptureEventCreate(
        workspace_id=workspace_id,
        tool=ToolName.SLACK,
        event_type=EventType.CORRECTION,
        actor_id=_hash_actor(workspace_id, actor_id),
        ai_output_id=f"slack:{previous.get('ts', ts)}",
        context_tags={"channel": channel},
        delta=[
            CorrectionDelta(
                field="message_content",
                change_type="content",
                change_summary="Human edited AI-generated Slack message",
            )
        ],
        confidence_signal=0.85,
        external_ref=ts,
    )

    service = EventCaptureService(conn)
    await service.ingest(capture)
    logger.info("slack_correction_captured", actor_id=actor_id, channel=channel)


async def _handle_rejection_reaction(event: dict, conn: AsyncConnection, workspace_id: str | None = None) -> None:
    """A thumbs-down / ❌ reaction on a bot message signals explicit rejection."""
    item = event.get("item", {})
    workspace_id = workspace_id or event.get("authed_users", ["unknown"])[0]

    capture = CaptureEventCreate(
        workspace_id=workspace_id,
        tool=ToolName.SLACK,
        event_type=EventType.REJECTION,
        actor_id=_hash_actor(workspace_id, event.get("user", "unknown")),
        ai_output_id=f"slack:{item.get('ts', '')}",
        context_tags={"channel": item.get("channel", "unknown"), "reaction": event.get("reaction")},
        delta=[
            CorrectionDelta(
                field="message_content",
                change_type="rejection",
                change_summary=f"Human added rejection reaction :{event.get('reaction')}: to AI message",
            )
        ],
        confidence_signal=0.90,
        external_ref=item.get("ts"),
    )

    service = EventCaptureService(conn)
    await service.ingest(capture)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_actor(workspace_id: str, user_id: str) -> str:
    """
    Pseudonymize the Slack user ID. We store a stable hash, not the raw ID.
    This means Lore cannot reverse-engineer who made a correction from the stored data.
    """
    import hashlib

    return hashlib.sha256(f"{workspace_id}:{user_id}".encode()).hexdigest()[:16]
