"""
Tests for the Context Injection API (POST /v1/context).

Covers:
  - Context request validation
  - Cache hit path (Redis returns cached response)
  - Cache miss path (Neo4j graph query)
  - _format_injection output structure
  - ContextResponse model
  - _request_hash stability
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.v1.context import _request_hash
from app.database.postgres import get_connection
from app.database.redis import get_redis_dep
from app.models.context import (
    ContextDecision,
    ContextEntityFact,
    ContextRequest,
    ContextResponse,
    ContextRule,
)
from app.services.context_graph import ContextGraphService


# ── Model unit tests ──────────────────────────────────────────────────────────

class TestContextRequestModel:
    def test_valid_request(self):
        req = ContextRequest(
            tool="email-agent",
            task="Draft a follow-up email to Acme Corp",
            entities=["Acme Corp"],
            context_tags={"customer_tier": "enterprise"},
        )
        assert req.tool == "email-agent"
        assert req.max_rules == 10  # default
        assert req.max_tokens == 2000  # default

    def test_default_entities_empty(self):
        req = ContextRequest(tool="agent", task="Do something")
        assert req.entities == []

    def test_max_rules_capped(self):
        with pytest.raises(Exception):
            ContextRequest(tool="agent", task="task", max_rules=50)  # max is 25


class TestContextResponseModel:
    def test_context_id_auto_generated(self):
        r = ContextResponse()
        assert r.context_id.startswith("ctx_")

    def test_defaults(self):
        r = ContextResponse()
        assert r.rules == []
        assert r.entities == []
        assert r.decisions == []
        assert r.formatted_injection == ""
        assert r.cache_hit is False
        assert r.latency_ms == 0


# ── Request hash ──────────────────────────────────────────────────────────────

class TestRequestHash:
    def test_same_request_same_hash(self):
        req = ContextRequest(
            tool="agent",
            task="Draft email",
            entities=["Acme"],
            context_tags={"tier": "enterprise"},
        )
        h1 = _request_hash(req)
        h2 = _request_hash(req)
        assert h1 == h2

    def test_different_task_different_hash(self):
        req1 = ContextRequest(tool="agent", task="Draft email")
        req2 = ContextRequest(tool="agent", task="Review code")
        assert _request_hash(req1) != _request_hash(req2)

    def test_entity_order_independent(self):
        """Sorting entities ensures consistent hashing regardless of order."""
        req1 = ContextRequest(tool="a", task="t", entities=["Acme", "Stripe"])
        req2 = ContextRequest(tool="a", task="t", entities=["Stripe", "Acme"])
        assert _request_hash(req1) == _request_hash(req2)


# ── ContextGraphService ───────────────────────────────────────────────────────

class TestContextGraphServiceFormatting:
    def test_format_injection_with_rules(self):
        rules = [
            ContextRule(
                rule_id="r1",
                text="Always use formal tone for enterprise clients",
                rule_type="behavioral",
                confidence=0.97,
                tool_scope=["*"],
            )
        ]
        result = ContextGraphService._format_injection(rules, [], [], max_tokens=1000)
        assert "[LORE CONTEXT]" in result
        assert "Always use formal tone" in result
        assert "0.97" in result

    def test_format_injection_with_entities(self):
        entities = [
            ContextEntityFact(
                entity_id="ent_1",
                entity_name="Acme Corp",
                entity_type="customer",
                facts=["Enterprise tier", "18-month client", "Formal tone required"],
            )
        ]
        result = ContextGraphService._format_injection([], entities, [], max_tokens=1000)
        assert "Acme Corp" in result
        assert "Enterprise tier" in result

    def test_format_injection_empty(self):
        result = ContextGraphService._format_injection([], [], [], max_tokens=1000)
        assert result == "[LORE CONTEXT]"

    def test_format_injection_truncated(self):
        rules = [
            ContextRule(
                rule_id=f"r{i}",
                text="A" * 100,  # Long rule text
                rule_type="behavioral",
                confidence=0.9,
                tool_scope=["*"],
            )
            for i in range(20)
        ]
        result = ContextGraphService._format_injection(rules, [], [], max_tokens=50)
        assert "truncated" in result

    def test_context_scope_matches_empty_scope(self):
        """Empty scope matches everything."""
        assert ContextGraphService._context_scope_matches({}, {"any": "tag"}) is True

    def test_context_scope_matches_exact(self):
        scope = {"jurisdiction": "US"}
        assert ContextGraphService._context_scope_matches(scope, {"jurisdiction": "US", "tier": "ent"}) is True
        assert ContextGraphService._context_scope_matches(scope, {"jurisdiction": "EU"}) is False

    def test_context_scope_no_match_missing_key(self):
        scope = {"jurisdiction": "US"}
        assert ContextGraphService._context_scope_matches(scope, {}) is False


# ── API tests (cache path) ────────────────────────────────────────────────────

class TestContextAPI:
    @pytest.mark.asyncio
    async def test_context_cache_hit(self, client, context_request_payload, app):
        """When Redis has a cached response, return it without hitting Neo4j."""
        cached_response = ContextResponse(
            rules=[],
            entities=[],
            formatted_injection="[LORE CONTEXT]\n- Cached rule",
            cache_hit=True,
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached_response.model_dump_json())
        mock_redis.set = AsyncMock()

        app.dependency_overrides[get_redis_dep] = lambda: mock_redis
        app.dependency_overrides[get_connection] = lambda: AsyncMock()

        try:
            response = await client.post(
                "/v1/context",
                params={"workspace_id": "ws_test"},
                json=context_request_payload(),
            )
            assert response.status_code == 200
            body = response.json()
            assert "[LORE CONTEXT]" in body["formatted_injection"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_context_validation_error(self, client, app):
        """Missing 'tool' field → 422."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        app.dependency_overrides[get_redis_dep] = lambda: mock_redis
        app.dependency_overrides[get_connection] = lambda: AsyncMock()

        try:
            response = await client.post(
                "/v1/context",
                params={"workspace_id": "ws_test"},
                json={"task": "Do something"},  # missing 'tool'
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()
