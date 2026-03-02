"""
RuleEngineService — manages the behavioral rule lifecycle in PostgreSQL.

Responsibilities:
  - CRUD for rules and proposals
  - Confirming proposals → creating active rules
  - Publishing rule confirmations back to the Neo4j graph via a background task
"""

import json
from datetime import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models.rules import (
    Rule,
    RuleConfirmRequest,
    RuleProposal,
    RuleStatus,
    RuleType,
    RuleUpdateRequest,
)

logger = structlog.get_logger(__name__)


class RuleEngineService:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    # ── Rules ─────────────────────────────────────────────────────────────────

    async def list_rules(
        self,
        workspace_id: str,
        status: RuleStatus | None = None,
        tool: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Rule], int]:
        offset = (page - 1) * page_size
        filters = "WHERE workspace_id = :ws"
        params: dict = {"ws": workspace_id, "limit": page_size, "offset": offset}

        if status:
            filters += " AND status = :status"
            params["status"] = status.value

        count_result = await self.conn.execute(
            text(f"SELECT COUNT(*) FROM rules {filters}"), params
        )
        total: int = count_result.scalar_one()

        rows_result = await self.conn.execute(
            text(f"SELECT * FROM rules {filters} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
            params,
        )
        items = [self._row_to_rule(dict(r)) for r in rows_result.mappings()]
        return items, total

    async def get_rule(self, rule_id: str) -> Rule | None:
        result = await self.conn.execute(
            text("SELECT * FROM rules WHERE rule_id = :id"), {"id": rule_id}
        )
        row = result.mappings().first()
        return self._row_to_rule(dict(row)) if row else None

    async def update_rule(self, rule_id: str, body: RuleUpdateRequest) -> Rule | None:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            return await self.get_rule(rule_id)

        set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = rule_id

        await self.conn.execute(
            text(f"UPDATE rules SET {set_clauses} WHERE rule_id = :id"), updates
        )
        await self.conn.commit()
        return await self.get_rule(rule_id)

    async def archive_rule(self, rule_id: str) -> bool:
        result = await self.conn.execute(
            text("UPDATE rules SET status = 'archived' WHERE rule_id = :id RETURNING rule_id"),
            {"id": rule_id},
        )
        await self.conn.commit()
        return result.rowcount > 0

    # ── Proposals ─────────────────────────────────────────────────────────────

    async def list_proposals(self, workspace_id: str) -> list[RuleProposal]:
        result = await self.conn.execute(
            text(
                "SELECT * FROM rule_proposals WHERE workspace_id = :ws AND reviewed = false ORDER BY created_at DESC"
            ),
            {"ws": workspace_id},
        )
        return [self._row_to_proposal(dict(r)) for r in result.mappings()]

    async def confirm_proposal(
        self, proposal_id: str, body: RuleConfirmRequest
    ) -> Rule | None:
        result = await self.conn.execute(
            text("SELECT * FROM rule_proposals WHERE proposal_id = :id AND reviewed = false"),
            {"id": proposal_id},
        )
        row = result.mappings().first()
        if not row:
            return None

        proposal = self._row_to_proposal(dict(row))

        # Create the confirmed rule
        rule = Rule(
            workspace_id=proposal.workspace_id,
            text=body.text or proposal.rule_text,
            rule_type=proposal.rule_type,
            tool_scope=body.tool_scope or proposal.tool_scope,
            context_scope=body.context_scope or proposal.context_scope,
            confidence=proposal.pattern_confidence,
            status=RuleStatus.ACTIVE,
            confirmed_by=body.confirmed_by,
            source_corrections=proposal.source_corrections,
        )

        await self.conn.execute(
            text(
                """
                INSERT INTO rules (
                    rule_id, workspace_id, text, rule_type, tool_scope, context_scope,
                    confidence, status, confirmed_by, source_corrections, created_at
                ) VALUES (
                    :rule_id, :workspace_id, :text, :rule_type, :tool_scope, :context_scope,
                    :confidence, :status, :confirmed_by, :source_corrections, :created_at
                )
                """
            ),
            {
                "rule_id": rule.rule_id,
                "workspace_id": rule.workspace_id,
                "text": rule.text,
                "rule_type": rule.rule_type.value,
                "tool_scope": json.dumps(rule.tool_scope),
                "context_scope": json.dumps(rule.context_scope),
                "confidence": rule.confidence,
                "status": rule.status.value,
                "confirmed_by": rule.confirmed_by,
                "source_corrections": json.dumps(rule.source_corrections),
                "created_at": rule.created_at,
            },
        )

        # Mark proposal as reviewed
        await self.conn.execute(
            text("UPDATE rule_proposals SET reviewed = true WHERE proposal_id = :id"),
            {"id": proposal_id},
        )
        await self.conn.commit()

        # Sync rule to Neo4j graph (background, non-blocking)
        await self._sync_rule_to_graph(rule)

        logger.info("rule_confirmed", rule_id=rule.rule_id, confirmed_by=body.confirmed_by)
        return rule

    async def dismiss_proposal(self, proposal_id: str) -> bool:
        result = await self.conn.execute(
            text(
                "UPDATE rule_proposals SET reviewed = true WHERE proposal_id = :id AND reviewed = false RETURNING proposal_id"
            ),
            {"id": proposal_id},
        )
        await self.conn.commit()
        return result.rowcount > 0

    # ── Graph sync ────────────────────────────────────────────────────────────

    async def _sync_rule_to_graph(self, rule: Rule) -> None:
        """
        Graph sync — no-op for MVP (Neo4j deferred to M6).
        Rules are queried directly from PostgreSQL by ContextGraphService.
        """
        logger.debug("rule_graph_sync_skipped", rule_id=rule.rule_id, reason="postgres_only_mvp")

    # ── Row mappers ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_col(value, default):
        """Supabase/asyncpg may return JSONB as already-parsed objects — handle both."""
        if value is None:
            return default
        if isinstance(value, str):
            return json.loads(value)
        return value  # already a dict/list

    @staticmethod
    def _row_to_rule(row: dict) -> Rule:
        row["tool_scope"] = RuleEngineService._parse_json_col(row.get("tool_scope"), ["*"])
        row["context_scope"] = RuleEngineService._parse_json_col(row.get("context_scope"), {})
        row["source_corrections"] = RuleEngineService._parse_json_col(row.get("source_corrections"), [])
        return Rule(**row)

    @staticmethod
    def _row_to_proposal(row: dict) -> RuleProposal:
        row["tool_scope"] = RuleEngineService._parse_json_col(row.get("tool_scope"), ["*"])
        row["context_scope"] = RuleEngineService._parse_json_col(row.get("context_scope"), {})
        row["source_corrections"] = RuleEngineService._parse_json_col(row.get("source_corrections"), [])
        row["example_summaries"] = RuleEngineService._parse_json_col(row.get("example_summaries"), [])
        return RuleProposal(**row)
