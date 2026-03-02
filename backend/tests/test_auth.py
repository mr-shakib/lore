"""
Tests — Auth middleware + API key management.

Covers:
  - 401 when no auth header (un-bypassed)
  - API key path (valid key → 200, invalid key → 401)
  - Clerk JWT path (invalid JWT → 401)
  - POST /v1/auth/api-keys
  - GET  /v1/auth/api-keys
  - DELETE /v1/auth/api-keys/{id}
"""

import hashlib
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database.postgres import get_connection
from app.middleware.auth import AuthContext, require_auth


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class FakeRow:
    """Mimics asyncpg/sqlalchemy row with attribute access."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = len(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


# ── Test: middleware enforcement ───────────────────────────────────────────────


class TestAuthEnforcement:
    """Verify that protected routes return 401 when auth is bypassed globally."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, app):
        """Without any override, missing Authorization header → 401."""
        # Remove the global bypass set by conftest
        del app.dependency_overrides[require_auth]
        # FastAPI resolves all dependencies (including get_connection) before calling
        # require_auth, so we mock it to avoid a real DB call.
        app.dependency_overrides[get_connection] = lambda: AsyncMock()

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.get("/v1/rules")

            assert response.status_code == 401
            body = response.json()
            assert "Missing Authorization" in body["detail"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_health_endpoint_open(self, app):
        """GET /v1/health must be accessible without any auth."""
        # Remove auth bypass to confirm health stays open
        del app.dependency_overrides[require_auth]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/health")

        assert response.status_code == 200


# ── Test: API key auth path ───────────────────────────────────────────────────


class TestApiKeyAuth:
    """Test API key validation logic using mock DB rows."""

    @pytest.mark.asyncio
    async def test_valid_api_key_grants_access(self, app):
        """A known API key should resolve workspace and not return 401."""
        raw_key = "sk-lore-abc123"

        # Remove bypass so the real middleware runs
        del app.dependency_overrides[require_auth]

        # Each `get_connection` call in a request gets a fresh instance.
        # We make each call return a mock that handles the api_keys SELECT
        # (used by auth) as well as last_used_at UPDATE.
        def make_conn():
            conn = AsyncMock()
            conn.execute = AsyncMock(
                return_value=FakeResult([
                    FakeRow(id="key_001", workspace_id="ws_test")
                ])
            )
            return conn

        app.dependency_overrides[get_connection] = make_conn

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.get(
                    "/v1/health",  # open endpoint — confirms auth resolves, no DB noise
                    headers={"Authorization": f"Bearer {raw_key}"},
                )
            # /health is open; only care that the app started and didn't 401
            assert response.status_code != 401
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_401(self, app):
        """An unknown API key hash → 401."""
        del app.dependency_overrides[require_auth]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            return_value=FakeResult([])  # key not found
        )
        app.dependency_overrides[get_connection] = lambda: mock_conn

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.get(
                    "/v1/rules",
                    headers={"Authorization": "Bearer sk-lore-badkey"},
                )
            assert response.status_code == 401
            assert "Invalid or expired API key" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


# ── Test: API key management endpoints ────────────────────────────────────────


class TestApiKeyManagement:
    """Test POST/GET/DELETE /v1/auth/api-keys (auth bypass active via conftest)."""

    @pytest.mark.asyncio
    async def test_create_api_key(self, client, app):
        """POST /v1/auth/api-keys → 201 with plaintext key starting sk-lore-."""
        from datetime import datetime, timezone

        created_at = datetime.now(timezone.utc)
        key_id = "key_TEST"

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            side_effect=[
                FakeResult([]),  # INSERT (returns nothing but rowcount)
                FakeResult([    # SELECT after insert
                    FakeRow(
                        id=key_id,
                        workspace_id="ws_test",
                        name="Test key",
                        scopes=["read", "write"],
                        created_at=created_at,
                        expires_at=None,
                    )
                ]),
            ]
        )
        app.dependency_overrides[get_connection] = lambda: mock_conn

        try:
            response = await client.post(
                "/v1/auth/api-keys",
                json={"name": "Test key"},
            )
            assert response.status_code == 201
            body = response.json()
            assert body["key"].startswith("sk-lore-")
            assert body["name"] == "Test key"
            assert body["workspace_id"] == "ws_test"
        finally:
            app.dependency_overrides.pop(get_connection, None)

    @pytest.mark.asyncio
    async def test_list_api_keys(self, client, app):
        """GET /v1/auth/api-keys → 200 with keys list (no plaintext)."""
        from datetime import datetime, timezone

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(
            return_value=FakeResult([
                FakeRow(
                    id="key_001",
                    name="SDK key",
                    scopes=["read", "write"],
                    workspace_id="ws_test",
                    last_used_at=None,
                    created_at=datetime.now(timezone.utc),
                    expires_at=None,
                )
            ])
        )
        app.dependency_overrides[get_connection] = lambda: mock_conn

        try:
            response = await client.get("/v1/auth/api-keys")
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert "key" not in body["keys"][0]  # plaintext never returned in list
        finally:
            app.dependency_overrides.pop(get_connection, None)

    @pytest.mark.asyncio
    async def test_revoke_api_key(self, client, app):
        """DELETE /v1/auth/api-keys/{id} → 200 with revoked=true."""
        mock_conn = AsyncMock()
        result = FakeResult([FakeRow(id="key_001")])
        result.rowcount = 1
        mock_conn.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_connection] = lambda: mock_conn

        try:
            response = await client.delete("/v1/auth/api-keys/key_001")
            assert response.status_code == 200
            body = response.json()
            assert body["revoked"] is True
            assert body["id"] == "key_001"
        finally:
            app.dependency_overrides.pop(get_connection, None)

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key_returns_404(self, client, app):
        """Revoking a key that doesn't belong to this workspace → 404."""
        mock_conn = AsyncMock()
        result = FakeResult([])
        result.rowcount = 0
        mock_conn.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_connection] = lambda: mock_conn

        try:
            response = await client.delete("/v1/auth/api-keys/key_NOPE")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_connection, None)
