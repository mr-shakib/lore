"""
PatternMiningService — clusters correction events and proposes behavioral rules.

Algorithm (pure Python + PostgreSQL, no vector DB required for MVP):
  1. Fetch unprocessed correction events per workspace from PostgreSQL
  2. Build a text fingerprint per event: tool + context_tags + delta change_summaries
  3. Use difflib.SequenceMatcher for pairwise similarity (trigram-equivalent in Python)
  4. Group events into clusters where pairwise similarity exceeds CLUSTER_SIMILARITY_THRESHOLD
  5. Discard clusters with < MIN_EVENTS_FOR_CLUSTER events or < MIN_ACTORS_FOR_CLUSTER unique actors
  6. Call Groq LLM (llama-3.3-70b-versatile, free tier) to generate a rule from each valid cluster
  7. Insert proposals into rule_proposals table
  8. Mark all processed events as processed = true

Design notes:
  - Pure Python clustering avoids pgvector/pg_trgm extension requirements at the DB layer
  - Groq free tier: 14,400 req/day, 500,000 tokens/min — no credit card required
  - Each mining pass processes up to 500 events per workspace to avoid memory pressure
  - Events already deduplicated upstream (5-min window in EventCaptureService)
  - A cluster requires events from ≥2 distinct actors to prevent a single user's habits
    from becoming company-wide rules
"""

import json
from datetime import UTC, datetime
from difflib import SequenceMatcher

import structlog
from groq import AsyncGroq
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.models.rules import RuleProposal, RuleType

logger = structlog.get_logger(__name__)

# ── Clustering thresholds ─────────────────────────────────────────────────────
# SequenceMatcher.ratio() returns 0-1 (proportion of matching characters in longest common subsequence).
# 0.55 is roughly equivalent to ~0.75 cosine similarity on short sentences.
CLUSTER_SIMILARITY_THRESHOLD = 0.55
MIN_EVENTS_FOR_CLUSTER = 3
MIN_ACTORS_FOR_CLUSTER = 2
MAX_EVENTS_PER_WORKSPACE = 500  # Sliding window — process oldest first


class PatternMiningService:
    """Stateless service — receives a DB connection, does one mining pass, returns stats."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn
        self._groq: AsyncGroq | None = None

    def _get_groq(self) -> AsyncGroq:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Pattern mining requires Groq. "
                "Get a free key at https://console.groq.com → API Keys."
            )
        if self._groq is None:
            self._groq = AsyncGroq(api_key=settings.groq_api_key)
        return self._groq

    # ── Public API ────────────────────────────────────────────────────────────

    async def run_mining_pass(self) -> dict[str, int]:
        """
        Execute one full mining pass across all workspaces.
        Returns a stats dict with counts for monitoring/logging.
        Safe to call multiple times — idempotent (events are marked processed after handling).
        """
        stats: dict[str, int] = {
            "workspaces_processed": 0,
            "events_processed": 0,
            "proposals_created": 0,
        }

        # Discover all workspaces that have unprocessed events
        ws_result = await self.conn.execute(
            text(
                "SELECT DISTINCT workspace_id FROM correction_events WHERE processed = FALSE"
            )
        )
        workspace_ids = [r[0] for r in ws_result.fetchall()]

        for workspace_id in workspace_ids:
            n_events, n_proposals = await self._mine_workspace(workspace_id)
            stats["workspaces_processed"] += 1
            stats["events_processed"] += n_events
            stats["proposals_created"] += n_proposals

        logger.info("pattern_mining_pass_complete", **stats)
        return stats

    # ── Per-workspace mining ──────────────────────────────────────────────────

    async def _mine_workspace(self, workspace_id: str) -> tuple[int, int]:
        """Mine one workspace. Returns (events_processed, proposals_created)."""
        events = await self._fetch_unprocessed_events(workspace_id)
        if not events:
            return 0, 0

        clusters = self._cluster_events(events)

        # Only process clusters meeting the quality bar
        valid_clusters = [
            cluster
            for cluster in clusters
            if len(cluster) >= MIN_EVENTS_FOR_CLUSTER
            and len({e["actor_id"] for e in cluster}) >= MIN_ACTORS_FOR_CLUSTER
        ]

        proposals_created = 0
        for cluster in valid_clusters:
            try:
                proposal = await self._generate_proposal(workspace_id, cluster)
                if proposal:
                    await self._save_proposal(proposal)
                    proposals_created += 1
            except Exception:
                logger.exception(
                    "proposal_generation_failed",
                    workspace_id=workspace_id,
                    cluster_size=len(cluster),
                )

        # Always mark all fetched events processed, regardless of clustering outcome.
        # This prevents re-processing events that didn't meet the threshold.
        event_ids = [e["event_id"] for e in events]
        await self._mark_processed(event_ids)
        await self.conn.commit()

        logger.info(
            "workspace_mined",
            workspace_id=workspace_id,
            events=len(events),
            valid_clusters=len(valid_clusters),
            proposals=proposals_created,
        )
        return len(events), proposals_created

    # ── DB operations ─────────────────────────────────────────────────────────

    async def _fetch_unprocessed_events(self, workspace_id: str) -> list[dict]:
        result = await self.conn.execute(
            text(
                """
                SELECT event_id, workspace_id, tool, actor_id,
                       context_tags, delta, timestamp
                FROM correction_events
                WHERE workspace_id = :ws
                  AND processed = FALSE
                ORDER BY timestamp ASC
                LIMIT :limit
                """
            ),
            {"ws": workspace_id, "limit": MAX_EVENTS_PER_WORKSPACE},
        )
        rows = []
        for row in result.mappings():
            r = dict(row)
            # Supabase returns JSONB columns as Python dicts/lists already,
            # but handle the string fallback for safety.
            if isinstance(r.get("context_tags"), str):
                r["context_tags"] = json.loads(r["context_tags"])
            r.setdefault("context_tags", {})
            if isinstance(r.get("delta"), str):
                r["delta"] = json.loads(r["delta"])
            r.setdefault("delta", [])
            rows.append(r)
        return rows

    async def _save_proposal(self, proposal: RuleProposal) -> None:
        await self.conn.execute(
            text(
                """
                INSERT INTO rule_proposals (
                    proposal_id, workspace_id, rule_text, rule_type,
                    tool_scope, context_scope, source_corrections,
                    pattern_confidence, llm_confidence, explanation,
                    example_summaries, created_at, reviewed
                ) VALUES (
                    :proposal_id, :workspace_id, :rule_text, :rule_type,
                    :tool_scope, :context_scope, :source_corrections,
                    :pattern_confidence, :llm_confidence, :explanation,
                    :example_summaries, :created_at, false
                )
                """
            ),
            {
                "proposal_id": proposal.proposal_id,
                "workspace_id": proposal.workspace_id,
                "rule_text": proposal.rule_text,
                "rule_type": proposal.rule_type.value,
                "tool_scope": json.dumps(proposal.tool_scope),
                "context_scope": json.dumps(proposal.context_scope),
                "source_corrections": json.dumps(proposal.source_corrections),
                "pattern_confidence": proposal.pattern_confidence,
                "llm_confidence": proposal.llm_confidence,
                "explanation": proposal.explanation,
                "example_summaries": json.dumps(proposal.example_summaries),
                "created_at": datetime.now(UTC),
            },
        )
        logger.info(
            "rule_proposal_created",
            proposal_id=proposal.proposal_id,
            workspace_id=proposal.workspace_id,
            rule_text=proposal.rule_text[:80],
            cluster_size=len(proposal.source_corrections),
        )

    async def _mark_processed(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        # SQLAlchemy text() with ANY(:ids) requires a Python list → asyncpg ARRAY
        await self.conn.execute(
            text(
                "UPDATE correction_events SET processed = true WHERE event_id = ANY(:ids)"
            ),
            {"ids": event_ids},
        )

    # ── Clustering ────────────────────────────────────────────────────────────

    def _event_fingerprint(self, event: dict) -> str:
        """
        Build a short, comparable text representation of an event.
        Includes: tool name, context tag key-values, and all delta change_summaries.
        """
        delta_text = " ".join(
            d.get("change_summary", "")
            for d in event.get("delta", [])
            if isinstance(d, dict)
        )
        tool = event.get("tool", "")
        tags = " ".join(
            f"{k}:{v}"
            for k, v in sorted((event.get("context_tags") or {}).items())
        )
        return f"{tool} {tags} {delta_text}".lower().strip()

    def _similarity(self, a: str, b: str) -> float:
        """Character-level similarity ratio using Python's built-in SequenceMatcher."""
        return SequenceMatcher(None, a, b).ratio()

    def _cluster_events(self, events: list[dict]) -> list[list[dict]]:
        """
        Greedy single-pass clustering.

        Each event is compared to the first cluster whose centroid fingerprint
        is similar enough (≥ CLUSTER_SIMILARITY_THRESHOLD). If no match is found,
        a new cluster is started with this event as the centroid.

        O(n × k) where k = number of distinct clusters (typically << n).
        Fast enough for ≤500 events per workspace.
        """
        fingerprints = [self._event_fingerprint(e) for e in events]
        clusters: list[list[int]] = []       # list of index lists
        centroids: list[str] = []            # representative fingerprint per cluster

        for i, fp in enumerate(fingerprints):
            placed = False
            for ci, centroid in enumerate(centroids):
                if self._similarity(fp, centroid) >= CLUSTER_SIMILARITY_THRESHOLD:
                    clusters[ci].append(i)
                    placed = True
                    break
            if not placed:
                clusters.append([i])
                centroids.append(fp)

        return [[events[idx] for idx in c] for c in clusters]

    # ── LLM rule generation ───────────────────────────────────────────────────

    async def _generate_proposal(
        self, workspace_id: str, cluster: list[dict]
    ) -> RuleProposal | None:
        """
        Call Groq to generate a behavioral rule from a correction cluster.
        Returns None if groq_api_key is missing or the LLM returns unparseable output.
        """
        if not settings.groq_api_key:
            logger.warning(
                "groq_api_key_missing",
                hint="Set GROQ_API_KEY to enable automatic rule proposals",
            )
            return None

        # Build privacy-safe example list (change summaries only — no raw content)
        summaries: list[str] = []
        for event in cluster[:5]:
            deltas = event.get("delta") or []
            if deltas and isinstance(deltas[0], dict):
                summary = deltas[0].get("change_summary", "").strip()
                if summary:
                    tool = event.get("tool", "unknown")
                    summaries.append(f"[{tool}] {summary}")

        if not summaries:
            return None

        unique_actors = len({e["actor_id"] for e in cluster})
        tool_name = cluster[0].get("tool", "unknown")

        prompt = (
            "You are analyzing human corrections to AI-generated outputs. "
            "Your job is to derive a behavioral rule that would prevent these "
            "corrections from being needed in the future.\n\n"
            f"Pattern: {len(cluster)} corrections from {unique_actors} different people follow the same pattern.\n\n"
            "Corrections:\n"
            + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(summaries))
            + "\n\n"
            "Generate a single behavioral rule an AI should follow to avoid these corrections.\n\n"
            "Respond ONLY with valid JSON — no markdown, no explanation outside JSON:\n"
            "{\n"
            '  "rule_text": "One sentence starting with Always or Never",\n'
            '  "rule_type": "behavioral" or "prohibition" or "entity" or "format",\n'
            '  "confidence": <float 0.0–1.0>,\n'
            '  "explanation": "1-2 sentences explaining why this pattern was detected"\n'
            "}"
        )

        groq = self._get_groq()
        response = await groq.chat.completions.create(
            model=settings.pattern_mining_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
        )

        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown code fences if the model wraps its response
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("proposal_json_parse_failed", raw=raw[:300])
            return None

        rule_text = data.get("rule_text", "").strip()
        if not rule_text:
            return None

        rule_type_str = data.get("rule_type", "behavioral")
        try:
            rule_type = RuleType(rule_type_str)
        except ValueError:
            rule_type = RuleType.BEHAVIORAL

        # Pattern confidence: scale with cluster size (more evidence = higher confidence)
        # Caps at 0.95 — humans must confirm before reaching 1.0
        pattern_confidence = round(min(0.95, 0.5 + len(cluster) * 0.05), 2)

        # Inherit the common context_scope from the cluster's first event
        context_scope = dict(cluster[0].get("context_tags") or {})

        return RuleProposal(
            workspace_id=workspace_id,
            rule_text=rule_text,
            rule_type=rule_type,
            tool_scope=[tool_name] if tool_name != "unknown" else ["*"],
            context_scope=context_scope,
            source_corrections=[e["event_id"] for e in cluster],
            pattern_confidence=pattern_confidence,
            llm_confidence=float(data.get("confidence", 0.8)),
            explanation=data.get("explanation", ""),
            example_summaries=summaries[:3],
        )
