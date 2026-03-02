"""
Event models — the core data structure flowing into Lore.

A CaptureEvent represents one moment of human-AI divergence:
the AI said X, the human did Y. Lore captures the delta.

Privacy guarantee: raw content (AI output text, human edit text) is
NEVER stored. Only structured diffs and metadata.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field
from ulid import ULID


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


# ── Enums ─────────────────────────────────────────────────────────────────────

class ToolName(str, Enum):
    """Connected tools / integration sources."""
    SLACK = "slack"
    GITHUB = "github"
    LINEAR = "linear"
    GMAIL = "gmail"
    NOTION = "notion"
    SALESFORCE = "salesforce"
    CUSTOM = "custom"       # Any agent using the Lore SDK directly


class EventType(str, Enum):
    """What the human did in response to the AI output."""
    CORRECTION = "correction"   # Human changed the AI output
    APPROVAL = "approval"       # Human accepted without changes (positive signal)
    REJECTION = "rejection"     # Human discarded and wrote their own
    OVERRIDE = "override"       # Human bypassed the AI entirely
    REROUTE = "reroute"         # Human changed an AI routing/assignment decision
    ANNOTATION = "annotation"   # Human added notes/context to the AI output


# ── Sub-models ────────────────────────────────────────────────────────────────

class CorrectionDelta(BaseModel):
    """
    A single semantic change within an event.
    One event may contain multiple deltas (e.g., tone change + removed pricing mention).
    """
    field: str
    """Which conceptual field was changed: 'tone', 'indemnity_clause', 'routing', etc."""

    change_type: str
    """Category of change: 'tone' | 'content' | 'format' | 'schema' | 'routing' | 'removal'."""

    change_summary: str
    """Human-readable, privacy-safe description of what changed (no raw content)."""


# ── Main event model ──────────────────────────────────────────────────────────

class CaptureEvent(BaseModel):
    """
    A fully-processed correction event stored in PostgreSQL and indexed in Neo4j.
    """
    event_id: str = Field(default_factory=lambda: _new_id("evt"))
    workspace_id: str
    tool: ToolName
    event_type: EventType
    actor_id: str
    """Pseudonymized identifier — a stable hash of email within the workspace."""

    ai_output_id: str | None = None
    """ID of the AI output this event relates to. Used to de-duplicate and link corrections."""

    context_tags: dict[str, str] = Field(default_factory=dict)
    """
    Key-value metadata attached by the source tool or SDK.
    Examples: {'customer_tier': 'enterprise', 'jurisdiction': 'US', 'task_category': 'email'}
    """

    delta: list[CorrectionDelta] = Field(default_factory=list)
    """Structured description of what the human changed."""

    confidence_signal: float = Field(default=1.0, ge=0.0, le=1.0)
    """
    How confident we are that this really is a meaningful correction.
    Integrations set this based on the signal quality (e.g., explicit correction = 1.0,
    vague edit = 0.6).
    """

    session_id: str | None = None
    """Groups events from the same human session (for deduplication)."""

    external_ref: str | None = None
    """Original ID in the source system (Slack message ts, GitHub comment ID, etc.)."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed: bool = False
    """True once the Pattern Mining Engine has evaluated this event."""

    processing_version: str | None = None
    """Version of the pattern mining engine that processed this event."""


# ── API input/output ──────────────────────────────────────────────────────────

class CaptureEventCreate(BaseModel):
    """
    Inbound payload accepted by POST /v1/events.
    Used by webhook adapters (Slack, GitHub, Linear) and the Lore SDK.
    """
    workspace_id: str
    tool: ToolName
    event_type: EventType
    actor_id: str
    ai_output_id: str | None = None
    context_tags: dict[str, str] = Field(default_factory=dict)
    delta: list[CorrectionDelta] = Field(default_factory=list)
    confidence_signal: float = Field(default=1.0, ge=0.0, le=1.0)
    session_id: str | None = None
    external_ref: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "workspace_id": "ws_01ABC",
                "tool": "slack",
                "event_type": "correction",
                "actor_id": "actor_hashed_abc123",
                "ai_output_id": "out_01XYZ",
                "context_tags": {"customer_tier": "enterprise", "channel": "sales"},
                "delta": [
                    {
                        "field": "tone",
                        "change_type": "tone",
                        "change_summary": "Changed from informal to formal register",
                    }
                ],
                "confidence_signal": 0.95,
            }
        }
    }


class CaptureEventResponse(BaseModel):
    """Response returned after a successful event ingestion."""
    event_id: str
    status: str = "queued"
    message: str = "Event accepted and queued for processing"
