"""
Entity models — the Entity Memory System.

Entities are first-class objects in the Company Context Graph.
They represent real-world things (customers, projects, code modules, concepts)
that appear repeatedly in correction events and decisions.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field
from ulid import ULID


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


# ── Enums ─────────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    CUSTOMER = "customer"
    PROJECT = "project"
    PRODUCT_FEATURE = "product_feature"
    EMPLOYEE = "employee"
    CODE_COMPONENT = "code_component"
    CONCEPT = "concept"     # e.g., "async DB pattern", "formal tone"
    OTHER = "other"


# ── Sub-models ────────────────────────────────────────────────────────────────

class EntityFact(BaseModel):
    """
    A single known fact about an entity.
    Facts accumulate as corrections and decisions reference the entity.
    """
    key: str
    """Semantic label for this fact: 'customer_tier', 'tone_preference', etc."""

    value: str
    """The fact content (privacy-safe — no PII beyond what's operationally necessary)."""

    source: str
    """Where this fact came from: 'correction' | 'decision' | 'manual'."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_confirmed: datetime | None = None


# ── Core model ────────────────────────────────────────────────────────────────

class Entity(BaseModel):
    """
    A persistent entity profile in the Company Context Graph.
    Auto-created when an entity name appears 3+ times in correction events.
    """
    entity_id: str = Field(default_factory=lambda: _new_id("ent"))
    workspace_id: str
    name: str
    name_lower: str = ""
    """Lowercase normalized name — used for fuzzy duplicate detection."""

    entity_type: EntityType
    facts: list[EntityFact] = Field(default_factory=list)

    linked_corrections: list[str] = Field(default_factory=list)
    """event_ids of corrections that reference this entity."""

    linked_decisions: list[str] = Field(default_factory=list)
    """decision_ids in the Decision Log that reference this entity."""

    linked_rules: list[str] = Field(default_factory=list)
    """rule_ids that apply specifically to this entity."""

    correction_rate: float | None = None
    """
    % of AI outputs involving this entity that required human correction.
    Higher = AI is less reliable when dealing with this entity.
    """

    is_stale: bool = False
    """Set to True if no new data for 180 days. De-prioritized in context injection."""

    is_permanently_relevant: bool = False
    """Admin flag — prevents entity from being marked stale."""

    mention_count: int = Field(default=0)
    """How many times this entity has appeared in events/decisions total."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def model_post_init(self, __context) -> None:
        if not self.name_lower:
            object.__setattr__(self, "name_lower", self.name.lower().strip())


# ── API input models ──────────────────────────────────────────────────────────

class EntityCreateRequest(BaseModel):
    """Body for POST /v1/entities (manual entity creation)."""
    workspace_id: str
    name: str
    entity_type: EntityType
    facts: list[EntityFact] = Field(default_factory=list)
    is_permanently_relevant: bool = False


class EntityUpdateRequest(BaseModel):
    """Body for PATCH /v1/entities/{entity_id}."""
    facts: list[EntityFact] | None = None
    is_permanently_relevant: bool | None = None
    entity_type: EntityType | None = None


class EntityListResponse(BaseModel):
    """Paginated entity list."""
    items: list[Entity]
    total: int
    page: int
    page_size: int
