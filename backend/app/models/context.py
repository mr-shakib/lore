"""
Context injection models.

The Context Injection API is Lore's core product endpoint.
A connected AI agent sends a ContextRequest before calling its LLM.
Lore returns a ContextResponse containing structured organizational context.
The agent prepends formatted_injection to its system prompt — done.
"""

from pydantic import BaseModel, Field
from ulid import ULID


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


# ── Request ───────────────────────────────────────────────────────────────────

class ContextRequest(BaseModel):
    """
    Sent by an AI agent to GET /v1/context before an LLM call.
    """
    tool: str
    """Identifier of the requesting AI tool (e.g., 'contract-drafting-agent')."""

    task: str
    """Natural language description of what the agent is about to do."""

    entities: list[str] = Field(default_factory=list)
    """
    Entity names the agent already knows are relevant.
    Examples: ['Acme Corp', 'Q1 Roadmap', 'auth-service']
    """

    context_tags: dict[str, str] = Field(default_factory=dict)
    """
    Additional key-value context for more precise rule matching.
    Examples: {'jurisdiction': 'US', 'customer_tier': 'enterprise'}
    """

    max_rules: int = Field(default=10, ge=1, le=25)
    """Maximum number of rules to include in the injection."""

    max_tokens: int = Field(default=2000, ge=100, le=4000)
    """Approximate token budget for the formatted injection block."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "contract-drafting-agent",
                "task": "Draft a Master Service Agreement for Acme Corp",
                "entities": ["Acme Corp"],
                "context_tags": {"jurisdiction": "US", "customer_tier": "enterprise"},
                "max_rules": 10,
                "max_tokens": 2000,
            }
        }
    }


# ── Response sub-models ───────────────────────────────────────────────────────

class ContextRule(BaseModel):
    """A single active rule included in the context response."""
    rule_id: str
    text: str
    rule_type: str
    confidence: float
    tool_scope: list[str]


class ContextEntityFact(BaseModel):
    """Known facts about a specific entity relevant to this request."""
    entity_id: str
    entity_name: str
    entity_type: str
    facts: list[str]
    correction_rate: float | None = None
    """What % of AI outputs for this entity were corrected (signal of AI unreliability here)."""


class ContextDecision(BaseModel):
    """A relevant past decision from the Decision Log."""
    decision_id: str
    title: str
    what_was_decided: str
    date: str


# ── Response ──────────────────────────────────────────────────────────────────

class ContextResponse(BaseModel):
    """
    Returned by POST /v1/context.
    The agent should prepend `formatted_injection` to its LLM system prompt.
    """
    context_id: str = Field(default_factory=lambda: _new_id("ctx"))
    rules: list[ContextRule] = Field(default_factory=list)
    entities: list[ContextEntityFact] = Field(default_factory=list)
    decisions: list[ContextDecision] = Field(default_factory=list)

    formatted_injection: str = ""
    """
    Pre-formatted string ready to be prepended to the LLM system prompt.
    Example:
      [LORE CONTEXT]
      - Always use US_STANDARD indemnity template for US clients (confidence: 0.97)
      - Acme Corp: enterprise tier, 18-month client, formal tone required
    """

    latency_ms: int = 0
    cache_hit: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "context_id": "ctx_01HABC",
                "rules": [
                    {
                        "rule_id": "rule_014",
                        "text": "US clients require US_STANDARD indemnity template",
                        "rule_type": "behavioral",
                        "confidence": 0.97,
                        "tool_scope": ["contract-drafting-agent"],
                    }
                ],
                "entities": [
                    {
                        "entity_id": "ent_ACME",
                        "entity_name": "Acme Corp",
                        "entity_type": "customer",
                        "facts": [
                            "Enterprise tier",
                            "18-month client",
                            "Primary contact prefers formal tone",
                            "Upsell paused pending onboarding review",
                        ],
                        "correction_rate": 0.30,
                    }
                ],
                "decisions": [],
                "formatted_injection": "[LORE CONTEXT]\n- US_STANDARD indemnity required for US clients\n- Acme Corp: enterprise, 18mo, formal tone, upsell paused",
                "latency_ms": 72,
                "cache_hit": False,
            }
        }
    }
