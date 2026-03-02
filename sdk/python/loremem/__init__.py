"""
loremem — The Python SDK for Lore Organizational Memory.

Quick start:
    from loremem import LoreClient

    client = LoreClient(
        api_key="sk-lore-xxxx",
        workspace_id="ws_yourworkspace",
    )

    # Before your LLM call
    ctx = client.get_context(query="Draft MSA for Acme Corp", tool="contract-agent")
    system_prompt = ctx.formatted_injection + base_system_prompt

    # After a human corrects the AI output
    client.report_correction(
        ai_output_id="output_001",
        summary="Changed jurisdiction from UK to US",
        tool="contract-agent",
    )
"""

from loremem.client import AsyncLoreClient, LoreClient
from loremem.models import ContextResponse, ReportResult

__version__ = "0.1.0"
__all__ = [
    "LoreClient",
    "AsyncLoreClient",
    "ContextResponse",
    "ReportResult",
]
