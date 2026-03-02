/** Public response types */

export interface RuleSnapshot {
  id: string;
  content: string;
  confidence: number;
  source?: string;
}

export interface EntitySnapshot {
  id: string;
  name: string;
  type: string;
}

export interface DecisionLog {
  rule_id: string;
  applied: boolean;
  reason?: string;
}

export interface ContextResponse {
  contextId: string;
  formattedInjection: string;
  rules: RuleSnapshot[];
  entities: EntitySnapshot[];
  decisions: DecisionLog[];
  cached: boolean;
  /** true if the SDK returned a safe empty default due to an error */
  isEmpty: boolean;
}

export function emptyContext(): ContextResponse {
  return {
    contextId: "",
    formattedInjection: "",
    rules: [],
    entities: [],
    decisions: [],
    cached: false,
    isEmpty: true,
  };
}

export interface ReportResult {
  accepted: boolean;
  eventId: string | null;
}

export function notAccepted(): ReportResult {
  return { accepted: false, eventId: null };
}

/** Options for getContext */
export interface GetContextOptions {
  query: string;
  tool: string;
  hints?: string[];
  entities?: string[];
  maxRules?: number;
  maxTokens?: number;
}

/** Options for reportCorrection */
export interface ReportCorrectionOptions {
  aiOutputId: string;
  summary: string;
  tool: string;
  contextTags?: string[];
  actorId?: string;
}

/** Options for reportOutput */
export interface ReportOutputOptions {
  outputId: string;
  tool: string;
  summary?: string;
  contextTags?: string[];
  actorId?: string;
}

/** Constructor options */
export interface LoreClientOptions {
  apiKey: string;
  workspaceId: string;
  baseUrl?: string;
}
