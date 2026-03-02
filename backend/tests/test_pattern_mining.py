"""
test_pattern_mining.py — unit tests for the Pattern Mining Service.

All tests use in-memory mocks. No real DB or LLM connections required.
Tests are marked with pytest-asyncio for async support.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pattern_mining import (
    CLUSTER_SIMILARITY_THRESHOLD,
    MIN_ACTORS_FOR_CLUSTER,
    MIN_EVENTS_FOR_CLUSTER,
    PatternMiningService,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    return conn


def _make_event(
    event_id: str,
    actor_id: str,
    tool: str = "slack",
    change_summary: str = "Human changed tone from informal to formal",
    context_tags: dict | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "workspace_id": "ws_test",
        "tool": tool,
        "actor_id": actor_id,
        "context_tags": context_tags or {"channel": "sales"},
        "delta": [
            {
                "field": "tone",
                "change_type": "tone",
                "change_summary": change_summary,
            }
        ],
        "timestamp": "2026-03-01T10:00:00Z",
    }


# ── Clustering tests ──────────────────────────────────────────────────────────

class TestClustering:
    def test_identical_events_grouped_together(self, mock_conn):
        """Events with the same summary string must end up in the same cluster."""
        service = PatternMiningService(mock_conn)
        events = [
            _make_event("evt_1", "actor_a", change_summary="Human changed tone from informal to formal"),
            _make_event("evt_2", "actor_b", change_summary="Human changed tone from informal to formal"),
            _make_event("evt_3", "actor_c", change_summary="Human changed tone from informal to formal"),
        ]
        clusters = service._cluster_events(events)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_similar_events_grouped_together(self, mock_conn):
        """Semantically similar summaries should land in the same cluster."""
        service = PatternMiningService(mock_conn)
        # Tone events share tool + tags + very similar summaries
        tone_context = {"channel": "sales"}
        events = [
            _make_event("evt_1", "actor_a", tool="slack", context_tags=tone_context,
                        change_summary="Human changed tone from informal to formal"),
            _make_event("evt_2", "actor_b", tool="slack", context_tags=tone_context,
                        change_summary="Human changed tone from informal to formal style"),
            _make_event("evt_3", "actor_c", tool="slack", context_tags=tone_context,
                        change_summary="Human changed tone to match formal requirements"),
            # Different tool + context + completely different summary → own cluster
            _make_event("evt_4", "actor_d", tool="github", context_tags={"repo": "backend"},
                        change_summary="Human removed deprecated print logs replaced with structured logger output"),
        ]
        clusters = service._cluster_events(events)
        # The tone cluster should be ≥2 events; the github event should be separate
        sizes = sorted([len(c) for c in clusters], reverse=True)
        assert sizes[0] >= 2  # At least 2 tone events grouped
        assert len(clusters) >= 2  # Github event is in its own cluster

    def test_dissimilar_events_each_in_own_cluster(self, mock_conn):
        """Three events with different tools, contexts, AND content should each be alone."""
        service = PatternMiningService(mock_conn)
        events = [
            _make_event("e1", "a1", tool="slack", context_tags={"channel": "sales"},
                        change_summary="Human changed tone from informal to formal in client email"),
            _make_event("e2", "a2", tool="github", context_tags={"repo": "api-service"},
                        change_summary="Human removed deprecated asyncio.coroutine decorator replaced with async def"),
            _make_event("e3", "a3", tool="linear", context_tags={"project": "infra-q2"},
                        change_summary="Human changed ticket priority from medium to critical for outage"),
        ]
        clusters = service._cluster_events(events)
        assert len(clusters) == 3

    def test_fingerprint_includes_tool_and_tags(self, mock_conn):
        """Fingerprint must contain the tool name and context tag values."""
        service = PatternMiningService(mock_conn)
        event = _make_event("e1", "a1", tool="github", change_summary="removed call")
        fp = service._event_fingerprint(event)
        assert "github" in fp
        assert "sales" in fp  # from context_tags: {"channel": "sales"}

    def test_fingerprint_empty_delta(self, mock_conn):
        """Fingerprint should not crash on events with an empty delta list."""
        service = PatternMiningService(mock_conn)
        event = _make_event("e1", "a1", change_summary="")
        event["delta"] = []
        fp = service._event_fingerprint(event)
        assert isinstance(fp, str)

    def test_similarity_identical_strings(self, mock_conn):
        service = PatternMiningService(mock_conn)
        assert service._similarity("hello world", "hello world") == 1.0

    def test_similarity_completely_different(self, mock_conn):
        service = PatternMiningService(mock_conn)
        assert service._similarity("hello world", "xyz abc 123 qwerty") < CLUSTER_SIMILARITY_THRESHOLD

    def test_similarity_partial_overlap(self, mock_conn):
        service = PatternMiningService(mock_conn)
        score = service._similarity("tone changed formal", "formal tone change requested")
        assert 0.0 < score < 1.0


# ── Cluster validation tests ──────────────────────────────────────────────────

class TestClusterValidation:
    def test_cluster_below_min_events_rejected(self, mock_conn):
        """Clusters with fewer than MIN_EVENTS_FOR_CLUSTER events must be filtered out."""
        service = PatternMiningService(mock_conn)
        cluster = [
            _make_event("e1", "actor_a"),
            _make_event("e2", "actor_b"),
        ]
        valid = [
            c for c in [cluster]
            if len(c) >= MIN_EVENTS_FOR_CLUSTER
            and len({e["actor_id"] for e in c}) >= MIN_ACTORS_FOR_CLUSTER
        ]
        assert len(valid) == 0

    def test_cluster_single_actor_rejected(self, mock_conn):
        """Clusters where all events share one actor must be filtered out (habits ≠ rules)."""
        service = PatternMiningService(mock_conn)
        cluster = [
            _make_event("e1", "actor_a"),
            _make_event("e2", "actor_a"),
            _make_event("e3", "actor_a"),
        ]
        valid = [
            c for c in [cluster]
            if len(c) >= MIN_EVENTS_FOR_CLUSTER
            and len({e["actor_id"] for e in c}) >= MIN_ACTORS_FOR_CLUSTER
        ]
        assert len(valid) == 0

    def test_cluster_meeting_threshold_accepted(self, mock_conn):
        """A cluster with ≥3 events from ≥2 distinct actors must be accepted."""
        cluster = [
            _make_event("e1", "actor_a"),
            _make_event("e2", "actor_b"),
            _make_event("e3", "actor_c"),
        ]
        valid = [
            c for c in [cluster]
            if len(c) >= MIN_EVENTS_FOR_CLUSTER
            and len({e["actor_id"] for e in c}) >= MIN_ACTORS_FOR_CLUSTER
        ]
        assert len(valid) == 1


# ── LLM proposal generation tests ────────────────────────────────────────────

class TestProposalGeneration:
    @pytest.mark.asyncio
    async def test_generate_proposal_returns_none_when_no_api_key(self, mock_conn):
        """If GROQ_API_KEY is empty, _generate_proposal must return None gracefully."""
        service = PatternMiningService(mock_conn)
        cluster = [_make_event(f"e{i}", f"actor_{i}") for i in range(3)]

        with patch("app.services.pattern_mining.settings") as mock_settings:
            mock_settings.groq_api_key = ""
            result = await service._generate_proposal("ws_test", cluster)

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_proposal_valid_cluster(self, mock_conn):
        """A valid cluster with a mocked LLM response should produce a RuleProposal."""
        service = PatternMiningService(mock_conn)
        cluster = [
            _make_event("e1", "actor_a", change_summary="Human changed tone from informal to formal in sales email"),
            _make_event("e2", "actor_b", change_summary="Human changed tone to formal for outbound message"),
            _make_event("e3", "actor_c", change_summary="Human adjusted message tone to formal business style"),
        ]

        mock_llm_json = json.dumps({
            "rule_text": "Always use formal business tone in outbound communications",
            "rule_type": "behavioral",
            "confidence": 0.88,
            "explanation": "Multiple team members consistently corrected informal tone in sales outreach.",
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_llm_json

        with patch("app.services.pattern_mining.settings") as mock_settings:
            mock_settings.groq_api_key = "test-key"
            mock_settings.pattern_mining_model = "llama-3.3-70b-versatile"

            mock_groq_client = AsyncMock()
            mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

            with patch.object(service, "_get_groq", return_value=mock_groq_client):
                proposal = await service._generate_proposal("ws_test", cluster)

        assert proposal is not None
        assert "formal" in proposal.rule_text.lower()
        assert proposal.workspace_id == "ws_test"
        assert len(proposal.source_corrections) == 3
        assert proposal.llm_confidence == 0.88
        assert proposal.rule_type.value == "behavioral"

    @pytest.mark.asyncio
    async def test_generate_proposal_handles_markdown_fences(self, mock_conn):
        """LLM sometimes wraps JSON in ```json fences — these must be stripped."""
        service = PatternMiningService(mock_conn)
        cluster = [_make_event(f"e{i}", f"actor_{i}") for i in range(3)]

        llm_json = json.dumps({
            "rule_text": "Never use informal greetings in enterprise communications",
            "rule_type": "prohibition",
            "confidence": 0.9,
            "explanation": "Users consistently removed informal greetings.",
        })
        fenced = f"```json\n{llm_json}\n```"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = fenced

        with patch("app.services.pattern_mining.settings") as mock_settings:
            mock_settings.groq_api_key = "test-key"
            mock_settings.pattern_mining_model = "llama-3.3-70b-versatile"

            mock_groq_client = AsyncMock()
            mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

            with patch.object(service, "_get_groq", return_value=mock_groq_client):
                proposal = await service._generate_proposal("ws_test", cluster)

        assert proposal is not None
        assert "informal" in proposal.rule_text.lower()

    @pytest.mark.asyncio
    async def test_generate_proposal_handles_bad_json(self, mock_conn):
        """If the LLM returns non-parseable output, _generate_proposal must return None."""
        service = PatternMiningService(mock_conn)
        cluster = [_make_event(f"e{i}", f"actor_{i}") for i in range(3)]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sorry, I cannot help with that."

        with patch("app.services.pattern_mining.settings") as mock_settings:
            mock_settings.groq_api_key = "test-key"
            mock_settings.pattern_mining_model = "llama-3.3-70b-versatile"

            mock_groq_client = AsyncMock()
            mock_groq_client.chat.completions.create = AsyncMock(return_value=mock_response)

            with patch.object(service, "_get_groq", return_value=mock_groq_client):
                proposal = await service._generate_proposal("ws_test", cluster)

        assert proposal is None


# ── DB operation tests ────────────────────────────────────────────────────────

class TestDbOperations:
    @pytest.mark.asyncio
    async def test_save_proposal_executes_insert(self, mock_conn):
        """_save_proposal must call conn.execute exactly once."""
        from app.models.rules import RuleProposal, RuleType

        service = PatternMiningService(mock_conn)
        proposal = RuleProposal(
            workspace_id="ws_test",
            rule_text="Always use formal tone",
            rule_type=RuleType.BEHAVIORAL,
            tool_scope=["slack"],
            context_scope={},
            source_corrections=["e1", "e2", "e3"],
            pattern_confidence=0.75,
            llm_confidence=0.85,
            explanation="Test explanation",
        )

        await service._save_proposal(proposal)
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_processed_calls_update(self, mock_conn):
        """_mark_processed must issue one UPDATE query."""
        service = PatternMiningService(mock_conn)
        await service._mark_processed(["e1", "e2", "e3"])
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_processed_empty_list_is_noop(self, mock_conn):
        """_mark_processed with no IDs should not touch the DB."""
        service = PatternMiningService(mock_conn)
        await service._mark_processed([])
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_mining_pass_no_workspaces(self, mock_conn):
        """When no unprocessed events exist, the pass returns zeroed stats."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.execute.return_value = mock_result

        service = PatternMiningService(mock_conn)
        stats = await service.run_mining_pass()

        assert stats["workspaces_processed"] == 0
        assert stats["events_processed"] == 0
        assert stats["proposals_created"] == 0
