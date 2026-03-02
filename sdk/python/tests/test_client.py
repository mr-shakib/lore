"""
Tests for loremem SDK.

Uses respx to mock httpx requests — no real network calls.
"""

from __future__ import annotations

import pytest
import respx
import httpx

from loremem import AsyncLoreClient, ContextResponse, LoreClient, ReportResult


_API_KEY = "sk-lore-test123"
_WORKSPACE = "ws_test"
_BASE = "http://localhost:8000"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> LoreClient:
    return LoreClient(api_key=_API_KEY, workspace_id=_WORKSPACE, base_url=_BASE)


@pytest.fixture
def async_client() -> AsyncLoreClient:
    return AsyncLoreClient(api_key=_API_KEY, workspace_id=_WORKSPACE, base_url=_BASE)


# ── Constructor validation ────────────────────────────────────────────────────


class TestConstructor:
    def test_missing_api_key_raises(self):
        with pytest.raises(ValueError, match="api_key"):
            LoreClient(api_key="", workspace_id="ws_test")

    def test_missing_workspace_raises(self):
        with pytest.raises(ValueError, match="workspace_id"):
            LoreClient(api_key="sk-lore-xxx", workspace_id="")

    def test_valid_construction(self):
        c = LoreClient(api_key="sk-lore-xxx", workspace_id="ws_test")
        assert c is not None


# ── get_context — happy path ──────────────────────────────────────────────────


class TestGetContext:
    @respx.mock
    def test_returns_context_response(self, client):
        respx.post(f"{_BASE}/v1/context").mock(
            return_value=httpx.Response(
                200,
                json={
                    "context_id": "ctx_001",
                    "formatted_injection": "[LORE CONTEXT]\n- Always use formal tone",
                    "rules": [{"id": "rule_001", "text": "Always use formal tone"}],
                    "entities": [],
                    "decisions": [],
                    "cached": False,
                },
            )
        )

        ctx = client.get_context(query="Draft email", tool="email-agent")

        assert isinstance(ctx, ContextResponse)
        assert ctx.context_id == "ctx_001"
        assert "[LORE CONTEXT]" in ctx.formatted_injection
        assert len(ctx.rules) == 1
        assert not ctx.cached
        assert bool(ctx)  # truthy when content present

    @respx.mock
    def test_includes_auth_header(self, client):
        request_captured = {}

        def capture(request):
            request_captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={
                "context_id": "ctx_002",
                "formatted_injection": "",
                "rules": [], "entities": [], "decisions": [], "cached": False,
            })

        respx.post(f"{_BASE}/v1/context").mock(side_effect=capture)
        client.get_context(query="test", tool="test-tool")

        assert request_captured["auth"] == f"Bearer {_API_KEY}"

    @respx.mock
    def test_cached_response(self, client):
        respx.post(f"{_BASE}/v1/context").mock(
            return_value=httpx.Response(200, json={
                "context_id": "ctx_003",
                "formatted_injection": "[LORE CONTEXT]\n- Rule A",
                "rules": [], "entities": [], "decisions": [], "cached": True,
            })
        )
        ctx = client.get_context(query="test", tool="agent")
        assert ctx.cached is True


# ── get_context — error handling (never-throw guarantee) ─────────────────────


class TestGetContextErrors:
    @respx.mock
    def test_network_error_returns_empty(self, client):
        respx.post(f"{_BASE}/v1/context").mock(side_effect=httpx.ConnectError("refused"))
        ctx = client.get_context(query="test", tool="agent")
        assert isinstance(ctx, ContextResponse)
        assert ctx.formatted_injection == ""
        assert not bool(ctx)  # falsy when empty

    @respx.mock
    def test_401_returns_empty(self, client):
        respx.post(f"{_BASE}/v1/context").mock(
            return_value=httpx.Response(401, json={"detail": "Invalid API key"})
        )
        ctx = client.get_context(query="test", tool="agent")
        assert ctx.formatted_injection == ""

    @respx.mock
    def test_500_retries_and_returns_empty(self, client):
        respx.post(f"{_BASE}/v1/context").mock(
            return_value=httpx.Response(500, json={"detail": "Internal server error"})
        )
        ctx = client.get_context(query="test", tool="agent")
        assert ctx.formatted_injection == ""

    @respx.mock
    def test_timeout_returns_empty(self, client):
        respx.post(f"{_BASE}/v1/context").mock(side_effect=httpx.TimeoutException("timeout"))
        ctx = client.get_context(query="test", tool="agent")
        assert ctx.formatted_injection == ""


# ── report_correction ─────────────────────────────────────────────────────────


class TestReportCorrection:
    @respx.mock
    def test_accepted(self, client):
        respx.post(f"{_BASE}/v1/events").mock(
            return_value=httpx.Response(202, json={"event_id": "evt_001", "status": "accepted"})
        )
        result = client.report_correction(
            ai_output_id="out_001",
            summary="Changed tone",
            tool="email-agent",
        )
        assert isinstance(result, ReportResult)
        assert result.accepted is True
        assert result.event_id == "evt_001"

    @respx.mock
    def test_network_error_returns_not_accepted(self, client):
        respx.post(f"{_BASE}/v1/events").mock(side_effect=httpx.ConnectError("refused"))
        result = client.report_correction(
            ai_output_id="out_001",
            summary="Changed tone",
            tool="email-agent",
        )
        assert result.accepted is False

    @respx.mock
    def test_sends_correct_payload(self, client):
        captured = {}

        def capture(request):
            captured["body"] = request.content
            return httpx.Response(202, json={"event_id": "evt_002"})

        respx.post(f"{_BASE}/v1/events").mock(side_effect=capture)
        client.report_correction(
            ai_output_id="out_002",
            summary="Fixed jurisdiction clause",
            tool="contract-agent",
            context_tags={"customer": "Acme Corp"},
            actor_id="james@company.com",
        )

        import json
        body = json.loads(captured["body"])
        assert body["event_type"] == "correction"
        assert body["ai_output_id"] == "out_002"
        assert body["actor_id"] == "james@company.com"
        assert body["context_tags"]["customer"] == "Acme Corp"


# ── report_output ─────────────────────────────────────────────────────────────


class TestReportOutput:
    @respx.mock
    def test_accepted(self, client):
        respx.post(f"{_BASE}/v1/events").mock(
            return_value=httpx.Response(202, json={"event_id": "evt_003"})
        )
        result = client.report_output(
            output_id="out_003",
            tool="email-agent",
            summary="Email approved",
        )
        assert result.accepted is True

    @respx.mock
    def test_sends_approval_event_type(self, client):
        captured = {}

        def capture(request):
            import json
            captured["body"] = json.loads(request.content)
            return httpx.Response(202, json={"event_id": "evt_004"})

        respx.post(f"{_BASE}/v1/events").mock(side_effect=capture)
        client.report_output(output_id="out_004", tool="email-agent")
        assert captured["body"]["event_type"] == "approval"


# ── Async client ──────────────────────────────────────────────────────────────


class TestAsyncClient:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_context_async(self, async_client):
        respx.post(f"{_BASE}/v1/context").mock(
            return_value=httpx.Response(200, json={
                "context_id": "ctx_async_001",
                "formatted_injection": "[LORE CONTEXT]\n- Use formal tone",
                "rules": [], "entities": [], "decisions": [], "cached": False,
            })
        )
        ctx = await async_client.get_context(query="Draft email", tool="email-agent")
        assert ctx.context_id == "ctx_async_001"
        assert bool(ctx)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_context_network_error_returns_empty(self, async_client):
        respx.post(f"{_BASE}/v1/context").mock(side_effect=httpx.ConnectError("refused"))
        ctx = await async_client.get_context(query="test", tool="agent")
        assert ctx.formatted_injection == ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_report_correction_async(self, async_client):
        respx.post(f"{_BASE}/v1/events").mock(
            return_value=httpx.Response(202, json={"event_id": "evt_async_001"})
        )
        result = await async_client.report_correction(
            ai_output_id="out_001",
            summary="Changed tone",
            tool="email-agent",
        )
        assert result.accepted is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_report_correction_error_returns_not_accepted(self, async_client):
        respx.post(f"{_BASE}/v1/events").mock(side_effect=httpx.ConnectError("refused"))
        result = await async_client.report_correction(
            ai_output_id="out_001", summary="test", tool="agent"
        )
        assert result.accepted is False
