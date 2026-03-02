# loremem — Python SDK for Lore

> Inject your company's organizational memory into any AI agent in 3 lines of code.

**Lore** captures every human correction of an AI output, structures it into a company knowledge graph, and feeds it back to your AI agents so they stop making the same mistakes twice.

`loremem` is the Python SDK for accessing Lore's Context Injection API.

---

## Installation

```bash
pip install loremem
```

---

## Quickstart (3 minutes)

```python
from loremem import LoreClient

client = LoreClient(
    api_key="sk-lore-xxxx",          # from POST /v1/auth/api-keys
    workspace_id="ws_yourworkspace",  # your Lore workspace ID
)

# ── Step 1: Get context before your LLM call ──────────────────────────────────

ctx = client.get_context(
    query="Draft an MSA for Acme Corp",
    tool="contract-drafting-agent",
    hints={"jurisdiction": "US", "customer_tier": "enterprise"},
    entities=["Acme Corp"],
)

# Prepend to your system prompt
system_prompt = ctx.formatted_injection + "\n\n" + YOUR_BASE_SYSTEM_PROMPT
response = openai_client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "system", "content": system_prompt}, ...],
)

# ── Step 2: Report corrections so Lore learns ─────────────────────────────────

# When a human edits the AI output:
client.report_correction(
    ai_output_id="draft_acme_msa_v1",
    summary="Changed indemnity clause from UK to US_STANDARD template",
    tool="contract-drafting-agent",
    context_tags={"customer": "Acme Corp", "document_type": "MSA"},
    actor_id="james@company.com",
)

# When a human approves the AI output without changes (positive signal):
client.report_output(
    output_id="draft_acme_msa_v2",
    tool="contract-drafting-agent",
    summary="MSA draft approved — no changes needed",
    actor_id="james@company.com",
)
```

After a few corrections, Lore automatically proposes rules like:
> *"US clients require the US_STANDARD indemnity template"*

Confirm the rule once → it's injected into every future AI call automatically.

---

## Async usage

For async agent frameworks (LangChain, CrewAI, FastAPI-based agents):

```python
from loremem import AsyncLoreClient

client = AsyncLoreClient(api_key="sk-lore-xxxx", workspace_id="ws_acme")

ctx = await client.get_context(
    query="Route this support ticket",
    tool="support-triage-agent",
)

await client.report_correction(
    ai_output_id="ticket_001",
    summary="Re-routed from Tier 1 to Enterprise team",
    tool="support-triage-agent",
)
```

---

## Never-throw guarantee

Every method in `LoreClient` and `AsyncLoreClient` is designed to **never raise exceptions**. If Lore is unavailable, misconfigured, or rate-limited:

- `get_context()` returns an empty `ContextResponse` (`.formatted_injection == ""`)
- `report_correction()` and `report_output()` return `ReportResult(accepted=False)`
- A `WARNING` is logged via Python's standard `logging` module

**Lore's unavailability will never cause your AI agent to break.**

```python
import logging
logging.getLogger("loremem").setLevel(logging.WARNING)  # optional: see SDK warnings
```

---

## API reference

### `LoreClient(api_key, workspace_id, base_url?)`

| Parameter | Type | Description |
|---|---|---|
| `api_key` | `str` | Lore API key (`sk-lore-...`) |
| `workspace_id` | `str` | Your workspace ID |
| `base_url` | `str` | Default: production Lore API. Set to `http://localhost:8000` for local dev |

### `get_context(query, tool, hints?, entities?, max_rules?, max_tokens?)`

Returns a `ContextResponse`:

| Field | Type | Description |
|---|---|---|
| `formatted_injection` | `str` | Ready-to-use string — prepend to system prompt |
| `context_id` | `str` | Unique ID for this context response |
| `rules` | `list[dict]` | Active rules that matched |
| `entities` | `list[dict]` | Entity profiles that matched |
| `decisions` | `list[dict]` | Decision records that matched |
| `cached` | `bool` | True if served from 15-min cache |

### `report_correction(ai_output_id, summary, tool, context_tags?, actor_id?)`

Call when a human edits or overrides an AI output.

### `report_output(output_id, tool, summary?, context_tags?, actor_id?)`

Call when a human approves an AI output unchanged (positive signal).

---

## Getting an API key

```bash
# Create a key (requires Clerk JWT from the dashboard, or bootstrap via Supabase directly)
curl -X POST https://lore-m0st.onrender.com/v1/auth/api-keys \
  -H "Authorization: Bearer <clerk_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production SDK key"}'
```

---

## Local development

```python
client = LoreClient(
    api_key="sk-lore-xxxx",
    workspace_id="ws_test",
    base_url="http://localhost:8000",  # local FastAPI server
)
```

---

## License

MIT
