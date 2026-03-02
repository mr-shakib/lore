"""
loremem data models.

Lightweight dataclasses — no Pydantic dependency in the SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextResponse:
    """
    Returned by LoreClient.get_context().

    In practice you mostly use `formatted_injection` — prepend it to your LLM
    system prompt. The other fields are available for logging / debugging.
    """

    context_id: str
    """Unique ID for this context response — include in your audit trail."""

    formatted_injection: str
    """
    Ready-to-use string to prepend to your LLM system prompt.
    Empty string when no relevant context exists or if the request failed.
    """

    rules: list[dict[str, Any]] = field(default_factory=list)
    """Active rules that matched this request."""

    entities: list[dict[str, Any]] = field(default_factory=list)
    """Entity profiles that matched this request."""

    decisions: list[dict[str, Any]] = field(default_factory=list)
    """Decision records that matched this request."""

    cached: bool = False
    """True if this response was served from cache (no graph query was run)."""

    @classmethod
    def empty(cls) -> "ContextResponse":
        """Safe empty response — returned on any error."""
        return cls(
            context_id="",
            formatted_injection="",
            rules=[],
            entities=[],
            decisions=[],
            cached=False,
        )

    def __bool__(self) -> bool:
        """True if the response contains any usable context."""
        return bool(self.formatted_injection)


@dataclass
class ReportResult:
    """Returned by report_correction / report_output. Always succeeds (errors swallowed)."""

    accepted: bool
    """True if the API accepted the report."""

    event_id: str = ""
    """Event ID assigned by Lore, if accepted."""
