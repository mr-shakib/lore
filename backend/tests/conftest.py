"""
conftest.py — shared pytest fixtures for all tests.

Provides:
  - app:         FastAPI app instance (no lifespan — overridden for tests)
  - client:      httpx.AsyncClient for making test requests
  - mock_redis:  In-memory Redis mock (fakeredis)
  - event_payload: Factory for CaptureEventCreate payloads
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import create_app


# ── App fixture (disables real DB lifespan) ───────────────────────────────────

@pytest.fixture
def app():
    """Return a fresh app instance without triggering the full lifespan."""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Async test client — use this in all API tests."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Mock dependencies ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_connection():
    """SQLAlchemy AsyncConnection mock."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    return conn


@pytest.fixture
def mock_redis():
    """Redis async client mock."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    return redis


# ── Data factories ─────────────────────────────────────────────────────────────

@pytest.fixture
def event_payload():
    """Factory function for CaptureEventCreate payloads."""
    def _make(**overrides):
        base = {
            "workspace_id": "ws_test",
            "tool": "slack",
            "event_type": "correction",
            "actor_id": "actor_abc123",
            "ai_output_id": "out_test_001",
            "context_tags": {"channel": "general"},
            "delta": [
                {
                    "field": "message_content",
                    "change_type": "tone",
                    "change_summary": "Human changed tone from informal to formal",
                }
            ],
            "confidence_signal": 0.9,
        }
        base.update(overrides)
        return base

    return _make


@pytest.fixture
def context_request_payload():
    """Factory for ContextRequest payloads."""
    def _make(**overrides):
        base = {
            "tool": "contract-drafting-agent",
            "task": "Draft an MSA for Acme Corp",
            "entities": ["Acme Corp"],
            "context_tags": {"jurisdiction": "US", "customer_tier": "enterprise"},
            "max_rules": 10,
            "max_tokens": 2000,
        }
        base.update(overrides)
        return base

    return _make
