# @lore-ai/sdk

TypeScript/JavaScript SDK for [Lore](https://github.com/mr-shakib/lore) — organizational AI memory.

Lore captures what your AI gets wrong, surfaces institutional rules at inference time, and improves over every loop.

---

## Install

```bash
# From npm (once published)
npm install @lore-ai/sdk

# From GitHub (current)
npm install github:mr-shakib/lore#main --prefix=sdk/typescript
```

---

## Quick Start

```typescript
import { LoreClient } from "@lore-ai/sdk";

const lore = new LoreClient({
  apiKey: process.env.LORE_API_KEY!,       // sk-lore-...
  workspaceId: process.env.LORE_WORKSPACE!, // ws_...
});

// 1. Get context before your LLM call
const ctx = await lore.getContext({
  query: "How should we handle refund requests from enterprise customers?",
  tool: "gpt-4o",
});

if (ctx.formattedInjection) {
  systemPrompt += "\n\n" + ctx.formattedInjection;
}

// 2. Report a correction when a human fixes an AI output
await lore.reportCorrection({
  aiOutputId: "msg_abc123",
  summary: "AI said 14-day refund window; actual policy is 30 days for enterprise",
  tool: "gpt-4o",
});

// 3. Report an approved output for memory reinforcement
await lore.reportOutput({
  outputId: "msg_xyz789",
  tool: "gpt-4o",
  summary: "Correctly cited 30-day enterprise refund window",
});
```

---

## API Reference

### `new LoreClient(options)`

| Option | Type | Required | Description |
|---|---|---|---|
| `apiKey` | `string` | ✅ | Bearer token starting with `sk-lore-` |
| `workspaceId` | `string` | ✅ | Your workspace identifier |
| `baseUrl` | `string` | — | Override API host (default: production URL) |

---

### `getContext(opts): Promise<ContextResponse>`

Fetches injected context rules for a specific AI tool call. **Never throws** — returns an empty `ContextResponse` (with `isEmpty: true`) on any error.

```typescript
const ctx = await lore.getContext({
  query: string,          // Natural language query
  tool: string,           // Tool/model identifier
  hints?: string[],       // Optional tag hints
  entities?: string[],    // Entity names to ground rules
  maxRules?: number,      // Max rules to return (default: 10)
  maxTokens?: number,     // Token budget (default: 2000)
});

ctx.contextId           // string
ctx.formattedInjection  // Markdown-formatted string to inject into system prompt
ctx.rules               // RuleSnapshot[]
ctx.entities            // EntitySnapshot[]
ctx.decisions           // DecisionLog[]
ctx.cached              // boolean
ctx.isEmpty             // true if this is a safe empty default
```

---

### `reportCorrection(opts): Promise<ReportResult>`

Records a human correction to an AI output. Triggers rule mining. **Never throws.**

```typescript
const result = await lore.reportCorrection({
  aiOutputId: string,      // ID of the AI message being corrected
  summary: string,         // Human-readable description of what was wrong
  tool: string,            // Tool that produced the output
  contextTags?: string[],  // Optional topic tags
  actorId?: string,        // User who made the correction
});

result.accepted   // boolean
result.eventId    // string | null
```

---

### `reportOutput(opts): Promise<ReportResult>`

Records an approved AI output. Reinforces relevant rules. **Never throws.**

```typescript
const result = await lore.reportOutput({
  outputId: string,        // ID of the approved AI message
  tool: string,            // Tool that produced the output
  summary?: string,        // Optional description
  contextTags?: string[],  // Optional topic tags
  actorId?: string,        // User who approved
});
```

---

## Retry Behaviour

The SDK automatically retries network errors and 5xx responses up to **3 times** with exponential backoff (0.5 s → 1 s → 2 s). `401`/`429` are not retried. Every method returns a safe default rather than throwing, so your AI pipeline stays running even if Lore is unavailable.

---

## Requirements

- Node.js ≥ 18 (uses native `fetch`)
- TypeScript ≥ 5.0 (optional — ships full `.d.ts`)
