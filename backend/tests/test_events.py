"""
Tests for the Event Capture API (POST /v1/events).

Covers:
  - Happy path event ingestion → 202 Accepted
  - Rate limit enforcement → 429
  - Deduplication (same actor+output within 5 min) → deduplicated response
  - Validation errors (missing required fields) → 422
  - CaptureEvent model construction and ULID generation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.postgres import get_connection
from app.database.redis import get_redis_dep
from app.models.events import CaptureEvent, CaptureEventCreate, EventType, ToolName


# ── Model unit tests ──────────────────────────────────────────────────────────

class TestCaptureEventModel:
    def test_event_id_auto_generated(self):
        event = CaptureEvent(
            workspace_id="ws_test",
            tool=ToolName.SLACK,
            event_type=EventType.CORRECTION,
            actor_id="actor_abc",
        )
        assert event.event_id.startswith("evt_")
        assert len(event.event_id) > 10

    def test_two_events_have_unique_ids(self):
        e1 = CaptureEvent(workspace_id="ws", tool=ToolName.SLACK, event_type=EventType.CORRECTION, actor_id="a")
        e2 = CaptureEvent(workspace_id="ws", tool=ToolName.SLACK, event_type=EventType.CORRECTION, actor_id="a")
        assert e1.event_id != e2.event_id

    def test_defaults(self):
        event = CaptureEvent(
            workspace_id="ws",
            tool=ToolName.GITHUB,
            event_type=EventType.APPROVAL,
            actor_id="actor_x",
        )
        assert event.context_tags == {}
        assert event.delta == []
        assert event.confidence_signal == 1.0
        assert event.processed is False

    def test_confidence_signal_clamped(self):
        with pytest.raises(Exception):
            CaptureEvent(
                workspace_id="ws",
                tool=ToolName.SLACK,
                event_type=EventType.CORRECTION,
                actor_id="a",
                confidence_signal=1.5,  # Out of range
            )

    def test_round_trip_serialization(self):
        event = CaptureEvent(
            workspace_id="ws_test",
            tool=ToolName.LINEAR,
            event_type=EventType.REROUTE,
            actor_id="actor_abc",
            context_tags={"priority": "high"},
        )
        data = event.model_dump()
        restored = CaptureEvent(**data)
        assert restored.event_id == event.event_id
        assert restored.workspace_id == event.workspace_id


# ── API tests ─────────────────────────────────────────────────────────────────

class TestEventIngestionAPI:
    @pytest.mark.asyncio
    async def test_ingest_event_success(self, client, event_payload, mock_db_connection, mock_redis, app):
        """Happy path: valid event returns 202 with event_id."""
        mock_db_connection.execute = AsyncMock(return_value=MagicMock(rowcount=1, scalar_one=MagicMock(return_value=0)))
        mock_db_connection.commit = AsyncMock()

        app.dependency_overrides[get_connection] = lambda: mock_db_connection
        app.dependency_overrides[get_redis_dep] = lambda: mock_redis

        try:
            response = await client.post("/v1/events", json=event_payload())
            assert response.status_code == 202
            body = response.json()
            assert "event_id" in body
            assert body["status"] == "queued"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ingest_event_missing_required_fields(self, client, mock_db_connection, mock_redis, app):
        """Missing workspace_id → 422 Unprocessable Entity."""
        app.dependency_overrides[get_connection] = lambda: mock_db_connection
        app.dependency_overrides[get_redis_dep] = lambda: mock_redis
        try:
            response = await client.post(
                "/v1/events",
                json={"tool": "slack", "event_type": "correction"},  # missing workspace_id, actor_id
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_ingest_event_invalid_tool(self, client, event_payload, mock_db_connection, mock_redis, app):
        """Unknown tool value → 422."""
        app.dependency_overrides[get_connection] = lambda: mock_db_connection
        app.dependency_overrides[get_redis_dep] = lambda: mock_redis
        try:
            payload = event_payload(tool="unknown_tool")
            response = await client.post("/v1/events", json=payload)
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, client, event_payload, mock_db_connection, app):
        """Exceed rate limit → 429."""
        mock_redis_over = AsyncMock()
        mock_redis_over.incr = AsyncMock(return_value=1001)  # Over limit of 1000
        mock_redis_over.expire = AsyncMock()

        app.dependency_overrides[get_connection] = lambda: mock_db_connection
        app.dependency_overrides[get_redis_dep] = lambda: mock_redis_over

        try:
            response = await client.post("/v1/events", json=event_payload())
            assert response.status_code == 429
            body = response.json()
            assert body["detail"]["error"] == "rate_limit_exceeded"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_deduplication(self, client, event_payload, mock_db_connection, app):
        """Same actor+output within dedup window → deduplicated response."""
        mock_redis_dup = AsyncMock()
        mock_redis_dup.incr = AsyncMock(return_value=1)
        mock_redis_dup.expire = AsyncMock()
        mock_redis_dup.set = AsyncMock(return_value=None)  # None = key already existed

        app.dependency_overrides[get_connection] = lambda: mock_db_connection
        app.dependency_overrides[get_redis_dep] = lambda: mock_redis_dup

        try:
            response = await client.post("/v1/events", json=event_payload())
            assert response.status_code == 202
            body = response.json()
            assert body["status"] == "deduplicated"
        finally:
            app.dependency_overrides.clear()


# ── Health checks ─────────────────────────────────────────────────────────────

class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_liveness(self, client):
        """GET /v1/health → 200 always."""
        response = await client.get("/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_root(self, client):
        """GET / → 200 with product info."""
        response = await client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["product"] == "Lore"
        assert "version" in body
