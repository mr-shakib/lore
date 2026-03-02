"""
GitHub integration — POST /v1/webhooks/github

Handles GitHub App webhook events:
  - pull_request_review             → "Changes requested" reviews correcting AI suggestions
  - pull_request_review_comment     → Inline comments correcting Copilot-suggested code

Security: GitHub signs requests with HMAC-SHA256 via X-Hub-Signature-256.

Permissions required in GitHub App:
  - pull_requests: read
  - No write access
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

# PR review states that indicate a human rejected/corrected AI-generated code
CORRECTION_STATES = {"changes_requested", "dismissed"}


# ── Signature verification ────────────────────────────────────────────────────

async def _verify_github_signature(request: Request) -> bytes:
    if not settings.github_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub integration not configured (missing GITHUB_WEBHOOK_SECRET).",
        )

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid GitHub signature.")

    return body


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("", summary="Receive GitHub App webhook payload")
async def github_webhook(
    request: Request,
    conn: AsyncConnection = Depends(get_connection),
    _body: bytes = Depends(_verify_github_signature),
) -> dict:
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(_body)

    if event_type == "pull_request_review":
        await _handle_pr_review(payload, conn)

    elif event_type == "pull_request_review_comment":
        await _handle_review_comment(payload, conn)

    return {"ok": True}


# ── Event handlers ────────────────────────────────────────────────────────────

async def _handle_pr_review(payload: dict, conn: AsyncConnection) -> None:
    """
    A PR review was submitted. If it's 'changes_requested', it may indicate
    the reviewer is correcting AI-generated code (Copilot, Cursor, etc.).
    """
    review = payload.get("review", {})
    state = review.get("state", "").lower()

    if state not in CORRECTION_STATES:
        return

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    workspace_id = str(repo.get("owner", {}).get("id", "unknown"))

    capture = CaptureEventCreate(
        workspace_id=workspace_id,
        tool=ToolName.GITHUB,
        event_type=EventType.CORRECTION,
        actor_id=_hash_actor(workspace_id, str(review.get("user", {}).get("id", "unknown"))),
        ai_output_id=f"github:pr:{pr.get('number', '')}",
        context_tags={
            "repo": repo.get("name", ""),
            "pr_number": str(pr.get("number", "")),
            "review_state": state,
        },
        delta=[
            CorrectionDelta(
                field="code",
                change_type="rejection",
                change_summary=f"PR review: changes requested on PR #{pr.get('number')} in {repo.get('name')}",
            )
        ],
        confidence_signal=0.80,
        external_ref=str(review.get("id", "")),
    )

    service = EventCaptureService(conn)
    await service.ingest(capture)
    logger.info("github_pr_review_captured", repo=repo.get("name"), pr=pr.get("number"))


async def _handle_review_comment(payload: dict, conn: AsyncConnection) -> None:
    """
    An inline review comment was left on a PR. These frequently correct
    Copilot-suggested code patterns.
    """
    comment = payload.get("comment", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    workspace_id = str(repo.get("owner", {}).get("id", "unknown"))

    # Only capture if the comment suggests an alternative (non-trivial heuristic at MVP)
    body_lower = comment.get("body", "").lower()
    correction_signals = ["should be", "should use", "use instead", "replace with", "avoid", "don't use", "deprecated"]
    is_correction = any(signal in body_lower for signal in correction_signals)

    if not is_correction:
        return

    capture = CaptureEventCreate(
        workspace_id=workspace_id,
        tool=ToolName.GITHUB,
        event_type=EventType.CORRECTION,
        actor_id=_hash_actor(workspace_id, str(comment.get("user", {}).get("id", "unknown"))),
        ai_output_id=f"github:pr:{pr.get('number', '')}:file:{comment.get('path', '')}",
        context_tags={
            "repo": repo.get("name", ""),
            "file_path": comment.get("path", ""),
            "diff_hunk_present": str(bool(comment.get("diff_hunk"))),
        },
        delta=[
            CorrectionDelta(
                field="code_pattern",
                change_type="content",
                change_summary=f"Inline correction on {comment.get('path', 'file')} in PR #{pr.get('number')}",
            )
        ],
        confidence_signal=0.75,
        external_ref=str(comment.get("id", "")),
    )

    service = EventCaptureService(conn)
    await service.ingest(capture)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_actor(workspace_id: str, user_id: str) -> str:
    return hashlib.sha256(f"{workspace_id}:{user_id}".encode()).hexdigest()[:16]
