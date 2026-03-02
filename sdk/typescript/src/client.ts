/**
 * LoreClient — synchronous-style (Promise-based) client for the Lore API.
 *
 * Never throws. All methods return safe defaults on error so your AI pipeline
 * keeps running even if Lore is unavailable.
 *
 * @example
 * ```typescript
 * import { LoreClient } from "@lore-ai/sdk";
 *
 * const lore = new LoreClient({
 *   apiKey: process.env.LORE_API_KEY!,
 *   workspaceId: process.env.LORE_WORKSPACE_ID!,
 * });
 *
 * const ctx = await lore.getContext({ query: "How should I handle PII?", tool: "gpt-4o" });
 * if (ctx.formattedInjection) {
 *   systemPrompt += "\n\n" + ctx.formattedInjection;
 * }
 * ```
 */

import { Transport } from "./http.js";
import {
  ContextResponse,
  emptyContext,
  GetContextOptions,
  LoreClientOptions,
  notAccepted,
  ReportCorrectionOptions,
  ReportOutputOptions,
  ReportResult,
} from "./models.js";

const DEFAULT_BASE_URL = "https://lore-m0st.onrender.com";

// ---- raw API response shapes (internal) ------------------------------------

interface RawContextResponse {
  context_id: string;
  formatted_injection: string;
  rules: Array<{ id: string; content: string; confidence: number; source?: string }>;
  entities: Array<{ id: string; name: string; type: string }>;
  decisions: Array<{ rule_id: string; applied: boolean; reason?: string }>;
  cached?: boolean;
}

interface RawEventResponse {
  event_id: string;
  accepted: boolean;
}

// ---- helpers ----------------------------------------------------------------

function mapContext(raw: RawContextResponse): ContextResponse {
  return {
    contextId: raw.context_id ?? "",
    formattedInjection: raw.formatted_injection ?? "",
    rules: raw.rules ?? [],
    entities: raw.entities ?? [],
    decisions: raw.decisions ?? [],
    cached: raw.cached ?? false,
    isEmpty: false,
  };
}

// ---- LoreClient (Promise-based) -------------------------------------------

export class LoreClient {
  private transport: Transport;

  constructor(opts: LoreClientOptions) {
    if (!opts.apiKey) throw new Error("apiKey is required");
    if (!opts.workspaceId) throw new Error("workspaceId is required");
    this.transport = new Transport({
      baseUrl: opts.baseUrl ?? DEFAULT_BASE_URL,
      apiKey: opts.apiKey,
      workspaceId: opts.workspaceId,
    });
  }

  /**
   * Retrieve context for an AI tool call.
   * Returns an empty ContextResponse on any error — never throws.
   */
  async getContext(opts: GetContextOptions): Promise<ContextResponse> {
    try {
      const raw = await this.transport.get<RawContextResponse>("/v1/context/resolve", {
        query: opts.query,
        tool: opts.tool,
        hints: opts.hints,
        entities: opts.entities,
        max_rules: opts.maxRules ?? 10,
        max_tokens: opts.maxTokens ?? 2000,
      });
      return mapContext(raw);
    } catch {
      return emptyContext();
    }
  }

  /**
   * Report a human correction to an AI output.
   * Returns `{ accepted: false, eventId: null }` on any error — never throws.
   */
  async reportCorrection(opts: ReportCorrectionOptions): Promise<ReportResult> {
    try {
      const raw = await this.transport.post<RawEventResponse>("/v1/events", {
        event_type: "correction",
        ai_output_id: opts.aiOutputId,
        summary: opts.summary,
        tool: opts.tool,
        context_tags: opts.contextTags ?? [],
        actor_id: opts.actorId,
      });
      return { accepted: raw.accepted ?? true, eventId: raw.event_id ?? null };
    } catch {
      return notAccepted();
    }
  }

  /**
   * Report an accepted AI output for memory reinforcement.
   * Returns `{ accepted: false, eventId: null }` on any error — never throws.
   */
  async reportOutput(opts: ReportOutputOptions): Promise<ReportResult> {
    try {
      const raw = await this.transport.post<RawEventResponse>("/v1/events", {
        event_type: "approval",
        output_id: opts.outputId,
        tool: opts.tool,
        summary: opts.summary,
        context_tags: opts.contextTags ?? [],
        actor_id: opts.actorId,
      });
      return { accepted: raw.accepted ?? true, eventId: raw.event_id ?? null };
    } catch {
      return notAccepted();
    }
  }
}
