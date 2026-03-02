"""
RuleEngineService — manages the behavioral rule lifecycle in PostgreSQL.

Responsibilities:
  - CRUD for rules and proposals
  - Confirming proposals → creating active rules
  - Publishing rule confirmations back to the Neo4j graph via a background task
"""

import json
from datetime import UTC, datetime

import structlog
from groq import AsyncGroq
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.models.rules import (
    ConflictResolveRequest,
    Rule,
    RuleConfirmRequest,
    RuleConfirmResponse,
    RuleProposal,
    RuleStatus,
    RuleType,
    RuleUpdateRequest,
)

logger = structlog.get_logger(__name__)


class RuleEngineService:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
        self._groq: AsyncGroq | None = None

    def _get_groq(self) -> AsyncGroq:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not set — conflict detection unavailable.")
        if self._groq is None:
            self._groq = AsyncGroq(api_key=settings.groq_api_key)
        return self._groq

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
    ) -> RuleConfirmResponse | None:
        result = await self.conn.execute(
            text("SELECT * FROM rule_proposals WHERE proposal_id = :id AND reviewed = false"),
            {"id": proposal_id},
        )
        row = result.mappings().first()
        if not row:
            return None

        proposal = self._row_to_proposal(dict(row))

        # Create the confirmed rule (initially active)
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
            last_supported=datetime.now(UTC),
        )

        await self.conn.execute(
            text(
                """
                INSERT INTO rules (
                    rule_id, workspace_id, text, rule_type, tool_scope, context_scope,
                    confidence, status, confirmed_by, source_corrections, created_at,
                    last_supported, conflict_with
                ) VALUES (
                    :rule_id, :workspace_id, :text, :rule_type, :tool_scope, :context_scope,
                    :confidence, :status, :confirmed_by, :source_corrections, :created_at,
                    :last_supported, :conflict_with
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
                "last_supported": rule.last_supported,
                "conflict_with": json.dumps([]),
            },
        )

        # Mark proposal as reviewed
        await self.conn.execute(
            text("UPDATE rule_proposals SET reviewed = true WHERE proposal_id = :id"),
            {"id": proposal_id},
        )
        await self.conn.commit()

        # ── Conflict detection ────────────────────────────────────────────────
        # Check existing active rules for semantic opposition.
        # Non-fatal: if Groq is unavailable, rule is confirmed as active without conflict check.
        conflicting_rules: list[Rule] = []
        try:
            conflict_ids = await self._detect_conflicts(rule)
            if conflict_ids:
                # Flag all conflicting pairs: both this rule and each conflicting rule
                for cid in conflict_ids:
                    await self.conn.execute(
                        text(
                            "UPDATE rules SET status = 'conflict', "
                            "conflict_with = :cw "
                            "WHERE rule_id = :id"
                        ),
                        {
                            "cw": json.dumps([cid]),
                            "id": rule.rule_id,
                        },
                    )
                    await self.conn.execute(
                        text(
                            "UPDATE rules SET status = 'conflict', "
                            "conflict_with = conflict_with || :cw::jsonb "
                            "WHERE rule_id = :id"
                        ),
                        {
                            "cw": json.dumps([rule.rule_id]),
                            "id": cid,
                        },
                    )
                    conflicting_rule = await self.get_rule(cid)
                    if conflicting_rule:
                        conflicting_rules.append(conflicting_rule)
                await self.conn.commit()
                rule.status = RuleStatus.CONFLICT
                rule.conflict_with = conflict_ids
                logger.warning(
                    "rule_conflict_detected",
                    new_rule_id=rule.rule_id,
                    conflicting_with=conflict_ids,
                )
        except Exception:
            logger.exception(
                "conflict_detection_failed",
                rule_id=rule.rule_id,
                hint="Rule confirmed as active without conflict check",
            )

        # Sync rule to Neo4j graph (background, non-blocking)
        await self._sync_rule_to_graph(rule)

        logger.info("rule_confirmed", rule_id=rule.rule_id, confirmed_by=body.confirmed_by)
        return RuleConfirmResponse(rule=rule, conflicts_detected=conflicting_rules)

    async def dismiss_proposal(self, proposal_id: str) -> bool:
        result = await self.conn.execute(
            text(
                "UPDATE rule_proposals SET reviewed = true WHERE proposal_id = :id AND reviewed = false RETURNING proposal_id"
            ),
            {"id": proposal_id},
        )
        await self.conn.commit()
        return result.rowcount > 0

    # ── Conflict resolution ───────────────────────────────────────────────────

    async def resolve_conflict(
        self, rule_id: str, body: ConflictResolveRequest
    ) -> Rule | None:
        """
        Resolve a conflict by either keeping this rule (archiving opponents)
        or archiving this rule (opponents remain/become active).

        action='keep'    → this rule → active,    conflict_with rules → archived
        action='archive' → this rule → archived,  conflict_with rules → active (if they were conflict)
        """
        rule = await self.get_rule(rule_id)
        if not rule or rule.status != RuleStatus.CONFLICT:
            return None

        if body.action == "keep":
            # Restore this rule to active, archive its opponents
            for cid in rule.conflict_with:
                await self.conn.execute(
                    text(
                        "UPDATE rules SET status = 'archived', conflict_with = '[]' "
                        "WHERE rule_id = :id AND status = 'conflict'"
                    ),
                    {"id": cid},
                )
            await self.conn.execute(
                text(
                    "UPDATE rules SET status = 'active', conflict_with = '[]' "
                    "WHERE rule_id = :id"
                ),
                {"id": rule_id},
            )
        else:
            # Archive this rule, restore the conflicting rules to active
            for cid in rule.conflict_with:
                await self.conn.execute(
                    text(
                        "UPDATE rules "
                        "SET status = 'active', "
                        "    conflict_with = (conflict_with - :remove_id::jsonb) "
                        "WHERE rule_id = :id AND status = 'conflict'"
                    ),
                    {"remove_id": json.dumps(rule_id), "id": cid},
                )
            await self.conn.execute(
                text(
                    "UPDATE rules SET status = 'archived', conflict_with = '[]' "
                    "WHERE rule_id = :id"
                ),
                {"id": rule_id},
            )

        await self.conn.commit()
        logger.info(
            "rule_conflict_resolved",
            rule_id=rule_id,
            action=body.action,
            resolved_by=body.resolved_by,
        )
        return await self.get_rule(rule_id)

    # ── Expiry checker ────────────────────────────────────────────────────────

    async def expire_stale_rules(self, days: int = 90) -> int:
        """
        Mark active rules as 'needs_review' if they have not seen supporting
        evidence in the last `days` days.

        Logic: COALESCE(last_supported, created_at) < NOW() - INTERVAL 'N days'
        This means a rule with no last_supported is evaluated against its creation date.

        Returns the number of rules transitioned to 'needs_review'.
        """
        result = await self.conn.execute(
            text(
                f"""
                UPDATE rules
                SET status = 'needs_review'
                WHERE status = 'active'
                  AND COALESCE(last_supported, created_at) < NOW() - INTERVAL '{days} days'
                RETURNING rule_id
                """
            )
        )
        count = result.rowcount
        await self.conn.commit()
        if count:
            logger.info("rules_marked_needs_review", count=count, days_threshold=days)
        return count

    # ── Conflict detection (Groq) ─────────────────────────────────────────────

    async def _detect_conflicts(self, new_rule: Rule) -> list[str]:
        """
        Use Groq to detect semantic conflicts between the new rule and all
        currently active rules in the same workspace.

        Returns a list of rule_ids that conflict with new_rule.
        Returns [] if no conflicts found, Groq unavailable, or on any error.
        """
        # Fetch all active rules in the workspace (excluding the new rule itself)
        result = await self.conn.execute(
            text(
                "SELECT rule_id, text FROM rules "
                "WHERE workspace_id = :ws AND status = 'active' AND rule_id != :rid"
            ),
            {"ws": new_rule.workspace_id, "rid": new_rule.rule_id},
        )
        active_rules = [dict(r) for r in result.mappings()]
        if not active_rules:
            return []

        # Build numbered list for the prompt
        rules_list = "\n".join(
            f"  {i + 1}. [id: {r['rule_id']}] {r['text']}"
            for i, r in enumerate(active_rules)
        )

        prompt = (
            "You are a rule conflict detector for an AI behavioral rules system.\n\n"
            f"New rule being confirmed:\n  \"{new_rule.text}\"\n\n"
            f"Existing active rules in the same workspace:\n{rules_list}\n\n"
            "A CONFLICT means two rules would give OPPOSING instructions for the same situation.\n"
            "Examples of conflicts:\n"
            "  - \"Always include pricing details\" vs \"Never include pricing details\" → CONFLICT\n"
            "  - \"Use formal language with clients\" vs \"Keep responses casual\" → CONFLICT\n"
            "  - \"Always include pricing details\" vs \"Use formal language\" → NO CONFLICT (different topics)\n\n"
            "Identify ONLY direct semantic conflicts. Return ONLY valid JSON — no markdown:\n"
            "{\"conflicting_rule_ids\": [\"rule_id_1\", \"rule_id_2\"]}\n"
            "If no conflicts: {\"conflicting_rule_ids\": []}"
        )

        groq = self._get_groq()
        response = await groq.chat.completions.create(
            model=settings.pattern_mining_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,   # Deterministic — conflict detection should be consistent
            max_tokens=200,
        )
        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown code fences
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("conflict_detection_json_parse_failed", raw=raw[:300])
            return []

        returned_ids: list[str] = data.get("conflicting_rule_ids", [])
        if not isinstance(returned_ids, list):
            return []

        # Validate: only accept IDs that actually exist in the active rules list
        valid_ids = {r["rule_id"] for r in active_rules}
        return [rid for rid in returned_ids if rid in valid_ids]



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
        row["conflict_with"] = RuleEngineService._parse_json_col(row.get("conflict_with"), [])
        return Rule(**row)

    @staticmethod
    def _row_to_proposal(row: dict) -> RuleProposal:
        row["tool_scope"] = RuleEngineService._parse_json_col(row.get("tool_scope"), ["*"])
        row["context_scope"] = RuleEngineService._parse_json_col(row.get("context_scope"), {})
        row["source_corrections"] = RuleEngineService._parse_json_col(row.get("source_corrections"), [])
        row["example_summaries"] = RuleEngineService._parse_json_col(row.get("example_summaries"), [])
        return RuleProposal(**row)
