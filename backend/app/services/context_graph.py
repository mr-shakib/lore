"""
ContextGraphService — queries PostgreSQL to assemble a ContextResponse
for the Context Injection API.

Replaces the Neo4j implementation for MVP (deferred to M6).
The service interface is identical — swapping back to a graph DB
only requires changes inside this file.

Assembly strategy:
  1. Fetch active rules matching the tool and context_tags (SQL + Python filter)
  2. Fetch entity profiles for requested entity names (case-insensitive)
  3. Fetch recent active decisions linked to the requested entities
  4. Format into a compact prompt injection string within the token budget
"""

import json

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.context import (
    ContextDecision,
    ContextEntityFact,
    ContextRequest,
    ContextResponse,
    ContextRule,
)

logger = structlog.get_logger(__name__)


class ContextGraphService:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    @staticmethod
    def _parse_json_col(value, default):
        """Handle JSONB columns that asyncpg/Supabase may return as already-parsed objects."""
        if value is None:
            return default
        if isinstance(value, str):
            return json.loads(value)
        return value

    async def assemble_context(
        self, workspace_id: str, request: ContextRequest
    ) -> ContextResponse:
        rules = await self._fetch_rules(workspace_id, request)
        entities = await self._fetch_entities(workspace_id, request)
        decisions = await self._fetch_decisions(workspace_id, request)

        formatted = self._format_injection(rules, entities, decisions, request.max_tokens)

        return ContextResponse(
            rules=rules,
            entities=entities,
            decisions=decisions,
            formatted_injection=formatted,
        )

    # ── SQL queries ───────────────────────────────────────────────────────────

    async def _fetch_rules(
        self, workspace_id: str, request: ContextRequest
    ) -> list[ContextRule]:
        """
        Fetch active rules matching workspace + tool scope.
        tool_scope is stored as a JSON array — check if it contains '*' or the requested tool.
        context_scope filtering applied in Python after fetch.
        """
        result = await self.conn.execute(
            text(
                """
                SELECT rule_id, text, rule_type, confidence, tool_scope, context_scope
                FROM rules
                WHERE workspace_id = :ws
                  AND status = 'active'
                  AND (
                      tool_scope::jsonb @> '["*"]'::jsonb
                      OR tool_scope::jsonb @> CAST(:tool_json AS jsonb)
                  )
                ORDER BY confidence DESC
                LIMIT :limit
                """
            ),
            {
                "ws": workspace_id,
                "tool_json": json.dumps([request.tool]),
                "limit": request.max_rules * 3,  # over-fetch before Python-side scope filter
            },
        )

        rules: list[ContextRule] = []
        for row in result.mappings():
            scope = self._parse_json_col(row["context_scope"], {})
            if self._context_scope_matches(scope, request.context_tags):
                rules.append(
                    ContextRule(
                        rule_id=row["rule_id"],
                        text=row["text"],
                        rule_type=row["rule_type"],
                        confidence=float(row["confidence"]),
                        tool_scope=self._parse_json_col(row["tool_scope"], ["*"]),
                    )
                )

        return rules[: request.max_rules]

    async def _fetch_entities(
        self, workspace_id: str, request: ContextRequest
    ) -> list[ContextEntityFact]:
        if not request.entities:
            return []

        names_lower = [e.lower().strip() for e in request.entities]
        placeholders = ", ".join(f":name_{i}" for i in range(len(names_lower)))
        params: dict = {"ws": workspace_id}
        for i, name in enumerate(names_lower):
            params[f"name_{i}"] = name

        result = await self.conn.execute(
            text(
                f"""
                SELECT entity_id, name, entity_type, facts
                FROM entities
                WHERE workspace_id = :ws
                  AND name_lower IN ({placeholders})
                  AND is_stale = false
                LIMIT 10
                """
            ),
            params,
        )

        entities: list[ContextEntityFact] = []
        for row in result.mappings():
            raw_facts = self._parse_json_col(row.get("facts"), [])
            facts_list: list[str] = []
            for f in raw_facts:
                if isinstance(f, dict):
                    facts_list.append(f"{f.get('key', '')}: {f.get('value', '')}")
                else:
                    facts_list.append(str(f))

            entities.append(
                ContextEntityFact(
                    entity_id=row["entity_id"],
                    entity_name=row["name"],
                    entity_type=row["entity_type"],
                    facts=facts_list,
                )
            )

        return entities

    async def _fetch_decisions(
        self, workspace_id: str, request: ContextRequest
    ) -> list[ContextDecision]:
        """
        Fetch 3 most recent active decisions.
        If entity names given, filter by linked_entities JSONB array.
        Post-MVP: replace with pgvector semantic search.
        """
        if not request.entities:
            result = await self.conn.execute(
                text(
                    """
                    SELECT decision_id, title, what_was_decided, date
                    FROM decisions
                    WHERE workspace_id = :ws AND status = 'active'
                    ORDER BY date DESC
                    LIMIT 3
                    """
                ),
                {"ws": workspace_id},
            )
        else:
            names_lower = [e.lower().strip() for e in request.entities]
            entity_filter = " OR ".join(
                f"linked_entities @> CAST(:n{i} AS jsonb)" for i in range(len(names_lower))
            )
            params2: dict = {"ws": workspace_id}
            for i, name in enumerate(names_lower):
                params2[f"n{i}"] = json.dumps([name])
            result = await self.conn.execute(
                text(
                    f"""
                    SELECT decision_id, title, what_was_decided, date
                    FROM decisions
                    WHERE workspace_id = :ws
                      AND status = 'active'
                      AND ({entity_filter})
                    ORDER BY date DESC
                    LIMIT 3
                    """
                ),
                params2,
            )

        decisions: list[ContextDecision] = []
        for row in result.mappings():
            decisions.append(
                ContextDecision(
                    decision_id=row["decision_id"],
                    title=row["title"],
                    what_was_decided=row["what_was_decided"] or "",
                    date=str(row["date"]) if row["date"] else "",
                )
            )

        return decisions

    # ── Formatting ────────────────────────────────────────────────────────────

    @staticmethod
    def _format_injection(
        rules: list[ContextRule],
        entities: list[ContextEntityFact],
        decisions: list[ContextDecision],
        max_tokens: int,
    ) -> str:
        """
        Build the [LORE CONTEXT] block that gets prepended to the LLM system prompt.
        Keeps output within a rough token budget (1 token ≈ 4 chars).
        """
        char_budget = max_tokens * 4
        lines: list[str] = ["[LORE CONTEXT]"]

        if rules:
            lines.append("Behavioral rules:")
            for r in rules:
                line = f"  - {r.text} (confidence: {r.confidence:.2f})"
                lines.append(line)

        if entities:
            lines.append("Entity context:")
            for e in entities:
                fact_str = "; ".join(e.facts[:5])  # Max 5 facts per entity
                line = f"  - {e.entity_name} ({e.entity_type}): {fact_str}"
                lines.append(line)

        if decisions:
            lines.append("Relevant decisions:")
            for d in decisions:
                line = f"  - [{d.date}] {d.title}: {d.what_was_decided}"
                lines.append(line)

        result = "\n".join(lines)
        # Truncate to budget if needed
        if len(result) > char_budget:
            result = result[:char_budget] + "\n  [context truncated to token budget]"

        return result

    @staticmethod
    def _context_scope_matches(scope: dict, tags: dict) -> bool:
        """
        Returns True if all keys in scope are present and matching in tags.
        An empty scope matches everything.
        """
        for key, value in scope.items():
            if tags.get(key) != value:
                return False
        return True
