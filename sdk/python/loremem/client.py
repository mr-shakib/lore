"""
LoreClient — sync and async clients for the Lore context injection API.

Sync usage (most AI agents):
    from loremem import LoreClient

    client = LoreClient(
        api_key="sk-lore-xxxx",
        workspace_id="ws_yourworkspace",
    )

    # Before every LLM call
    context = client.get_context(
        query="Draft an MSA for Acme Corp",
        tool="contract-drafting-agent",
    )
    # context.formatted_injection → prepend to system prompt

Async usage (async agent frameworks — LangChain, CrewAI, etc.):
    from loremem import AsyncLoreClient

    client = AsyncLoreClient(api_key="sk-lore-xxxx", workspace_id="ws_acme")
    context = await client.get_context(query="...", tool="...")
"""

from __future__ import annotations

import logging
from typing import Any

from loremem._http import AsyncTransport, Transport, _CONTEXT_TIMEOUT
from loremem.exceptions import LoreMemError
from loremem.models import ContextResponse, ReportResult

logger = logging.getLogger("loremem")

_DEFAULT_BASE_URL = "https://lore-m0st.onrender.com"


# ── Sync client ───────────────────────────────────────────────────────────────


class LoreClient:
    """
    Synchronous Lore client.

    Parameters
    ----------
    api_key:
        Your Lore API key (starts with ``sk-lore-``). Get one from
        ``POST /v1/auth/api-keys`` or the Lore dashboard.
    workspace_id:
        The workspace this client operates within.
    base_url:
        Override the API base URL (default: production Render service).
        Set to ``http://localhost:8000`` during local development.
    """

    def __init__(
        self,
        api_key: str,
        workspace_id: str,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty.")
        if not workspace_id:
            raise ValueError("workspace_id must not be empty.")

        self._workspace_id = workspace_id
        self._http = Transport(base_url=base_url, api_key=api_key)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_context(
        self,
        query: str,
        tool: str,
        hints: dict[str, Any] | None = None,
        entities: list[str] | None = None,
        max_rules: int = 10,
        max_tokens: int = 2000,
    ) -> ContextResponse:
        """
        Retrieve relevant organizational context for an AI task.

        Call this **before** your LLM call and prepend
        ``response.formatted_injection`` to your system prompt.

        This method **never raises**. On any error it returns an empty
        ``ContextResponse`` and logs a warning so your agent continues normally.

        Parameters
        ----------
        query:
            Natural language description of the task the agent is about to perform.
            E.g. ``"Draft an MSA for Acme Corp"``.
        tool:
            Identifier for the AI tool making the request. Use a consistent slug
            per agent — e.g. ``"contract-drafting-agent"``. Rules are scoped to tool.
        hints:
            Optional dict of additional context tags passed to the graph query.
            E.g. ``{"jurisdiction": "US", "customer_tier": "enterprise"}``.
        entities:
            Optional list of entity names to fetch specific profiles for.
            E.g. ``["Acme Corp"]``.
        max_rules:
            Maximum number of rules to include in the injection block.
        max_tokens:
            Approximate token budget for the formatted injection string.

        Returns
        -------
        ContextResponse
            Always returns a valid object. ``formatted_injection`` is an empty
            string when no context was found or on error.

        Example
        -------
        ::

            ctx = client.get_context(
                query="Draft an MSA for Acme Corp",
                tool="contract-agent",
                hints={"jurisdiction": "US"},
                entities=["Acme Corp"],
            )
            system_prompt = ctx.formatted_injection + "\\n\\n" + base_system_prompt
        """
        try:
            payload: dict[str, Any] = {
                "tool": tool,
                "task": query,
                "context_tags": hints or {},
                "entities": entities or [],
                "max_rules": max_rules,
                "max_tokens": max_tokens,
            }
            data = self._http.post(
                f"/v1/context?workspace_id={self._workspace_id}",
                payload=payload,
                timeout=_CONTEXT_TIMEOUT,
            )
            return ContextResponse(
                context_id=data.get("context_id", ""),
                formatted_injection=data.get("formatted_injection", ""),
                rules=data.get("rules", []),
                entities=data.get("entities", []),
                decisions=data.get("decisions", []),
                cached=data.get("cached", False),
            )
        except LoreMemError as exc:
            logger.warning("loremem.get_context failed — returning empty context: %s", exc)
            return ContextResponse.empty()
        except Exception as exc:
            logger.warning("loremem.get_context unexpected error — returning empty context: %s", exc)
            return ContextResponse.empty()

    def report_correction(
        self,
        ai_output_id: str,
        summary: str,
        tool: str,
        context_tags: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> ReportResult:
        """
        Report a human correction of an AI output.

        Call this whenever a human edits, overrides, or rejects an AI-generated
        output. Lore learns from these corrections over time.

        This method **never raises**. Errors are logged as warnings.

        Parameters
        ----------
        ai_output_id:
            ID you assigned to the AI output that was corrected. Used for
            deduplication and linking back to the original output.
        summary:
            Human-readable description of what changed.
            E.g. ``"Changed jurisdiction clause from UK to US standard"``.
        tool:
            The tool that generated the original output. Same slug as in
            ``get_context()``.
        context_tags:
            Optional additional metadata about the correction context.
            E.g. ``{"customer": "Acme Corp", "document_type": "MSA"}``.
        actor_id:
            ID of the human who made the correction (email or user ID).
            Helps pattern mining distinguish corrections by different people.

        Returns
        -------
        ReportResult
            Always returns. ``accepted=True`` means the event was queued.

        Example
        -------
        ::

            client.report_correction(
                ai_output_id="draft_acme_msa_v1",
                summary="Changed indemnity clause to US_STANDARD template",
                tool="contract-agent",
                context_tags={"customer": "Acme Corp"},
                actor_id="james@company.com",
            )
        """
        try:
            payload: dict[str, Any] = {
                "workspace_id": self._workspace_id,
                "tool": tool,
                "event_type": "correction",
                "ai_output_id": ai_output_id,
                "actor_id": actor_id or "sdk_reporter",
                "context_tags": context_tags or {},
                "delta": [
                    {
                        "field": "output",
                        "change_type": "correction",
                        "change_summary": summary,
                    }
                ],
                "confidence_signal": 0.9,
            }
            data = self._http.post(
                f"/v1/events?workspace_id={self._workspace_id}",
                payload=payload,
            )
            return ReportResult(
                accepted=True,
                event_id=data.get("event_id", ""),
            )
        except LoreMemError as exc:
            logger.warning("loremem.report_correction failed (event dropped): %s", exc)
            return ReportResult(accepted=False)
        except Exception as exc:
            logger.warning("loremem.report_correction unexpected error (event dropped): %s", exc)
            return ReportResult(accepted=False)

    def report_output(
        self,
        output_id: str,
        tool: str,
        summary: str = "",
        context_tags: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> ReportResult:
        """
        Report an AI output that was approved without modification (positive signal).

        Use this when a human reviews an AI output and accepts it without changes.
        This reinforces the rules that contributed to the good output.

        This method **never raises**.

        Parameters
        ----------
        output_id:
            Unique ID for this AI output — the same ID you'd pass to
            ``report_correction()`` if the output were later corrected.
        tool:
            The tool that generated this output.
        summary:
            Optional description of what was generated. E.g. ``"MSA draft approved"``.
        context_tags:
            Optional metadata about the output context.
        actor_id:
            ID of the human who approved the output.

        Returns
        -------
        ReportResult
        """
        try:
            payload: dict[str, Any] = {
                "workspace_id": self._workspace_id,
                "tool": tool,
                "event_type": "approval",
                "ai_output_id": output_id,
                "actor_id": actor_id or "sdk_reporter",
                "context_tags": context_tags or {},
                "delta": [
                    {
                        "field": "output",
                        "change_type": "approval",
                        "change_summary": summary or "Output approved without modification",
                    }
                ],
                "confidence_signal": 1.0,
            }
            data = self._http.post(
                f"/v1/events?workspace_id={self._workspace_id}",
                payload=payload,
            )
            return ReportResult(
                accepted=True,
                event_id=data.get("event_id", ""),
            )
        except LoreMemError as exc:
            logger.warning("loremem.report_output failed (event dropped): %s", exc)
            return ReportResult(accepted=False)
        except Exception as exc:
            logger.warning("loremem.report_output unexpected error (event dropped): %s", exc)
            return ReportResult(accepted=False)


# ── Async client ──────────────────────────────────────────────────────────────


class AsyncLoreClient:
    """
    Async variant of LoreClient. Same interface, all methods are coroutines.

    Use with async agent frameworks (LangChain, CrewAI, FastAPI-based agents, etc.).

    ::

        client = AsyncLoreClient(api_key="sk-lore-xxx", workspace_id="ws_acme")
        ctx = await client.get_context(query="...", tool="...")
    """

    def __init__(
        self,
        api_key: str,
        workspace_id: str,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty.")
        if not workspace_id:
            raise ValueError("workspace_id must not be empty.")

        self._workspace_id = workspace_id
        self._http = AsyncTransport(base_url=base_url, api_key=api_key)

    async def get_context(
        self,
        query: str,
        tool: str,
        hints: dict[str, Any] | None = None,
        entities: list[str] | None = None,
        max_rules: int = 10,
        max_tokens: int = 2000,
    ) -> ContextResponse:
        """Async version of LoreClient.get_context(). Never raises."""
        try:
            payload: dict[str, Any] = {
                "tool": tool,
                "task": query,
                "context_tags": hints or {},
                "entities": entities or [],
                "max_rules": max_rules,
                "max_tokens": max_tokens,
            }
            data = await self._http.post(
                f"/v1/context?workspace_id={self._workspace_id}",
                payload=payload,
                timeout=_CONTEXT_TIMEOUT,
            )
            return ContextResponse(
                context_id=data.get("context_id", ""),
                formatted_injection=data.get("formatted_injection", ""),
                rules=data.get("rules", []),
                entities=data.get("entities", []),
                decisions=data.get("decisions", []),
                cached=data.get("cached", False),
            )
        except Exception as exc:
            logger.warning("loremem.get_context failed — returning empty context: %s", exc)
            return ContextResponse.empty()

    async def report_correction(
        self,
        ai_output_id: str,
        summary: str,
        tool: str,
        context_tags: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> ReportResult:
        """Async version of LoreClient.report_correction(). Never raises."""
        try:
            payload: dict[str, Any] = {
                "workspace_id": self._workspace_id,
                "tool": tool,
                "event_type": "correction",
                "ai_output_id": ai_output_id,
                "actor_id": actor_id or "sdk_reporter",
                "context_tags": context_tags or {},
                "delta": [
                    {
                        "field": "output",
                        "change_type": "correction",
                        "change_summary": summary,
                    }
                ],
                "confidence_signal": 0.9,
            }
            data = await self._http.post(
                f"/v1/events?workspace_id={self._workspace_id}",
                payload=payload,
            )
            return ReportResult(accepted=True, event_id=data.get("event_id", ""))
        except Exception as exc:
            logger.warning("loremem.report_correction failed (event dropped): %s", exc)
            return ReportResult(accepted=False)

    async def report_output(
        self,
        output_id: str,
        tool: str,
        summary: str = "",
        context_tags: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> ReportResult:
        """Async version of LoreClient.report_output(). Never raises."""
        try:
            payload: dict[str, Any] = {
                "workspace_id": self._workspace_id,
                "tool": tool,
                "event_type": "approval",
                "ai_output_id": output_id,
                "actor_id": actor_id or "sdk_reporter",
                "context_tags": context_tags or {},
                "delta": [
                    {
                        "field": "output",
                        "change_type": "approval",
                        "change_summary": summary or "Output approved without modification",
                    }
                ],
                "confidence_signal": 1.0,
            }
            data = await self._http.post(
                f"/v1/events?workspace_id={self._workspace_id}",
                payload=payload,
            )
            return ReportResult(accepted=True, event_id=data.get("event_id", ""))
        except Exception as exc:
            logger.warning("loremem.report_output failed (event dropped): %s", exc)
            return ReportResult(accepted=False)
