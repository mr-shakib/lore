/**
 * Server-side API client for the Lore backend.
 * All functions are safe to call from Server Components and Server Actions.
 * Uses LORE_API_KEY + LORE_WORKSPACE_ID from environment.
 */

const BASE_URL = process.env.LORE_API_URL ?? "https://lore-m0st.onrender.com";
const API_KEY = process.env.LORE_API_KEY ?? "";
const WORKSPACE_ID = process.env.LORE_WORKSPACE_ID ?? "";

function headers(): Record<string, string> {
  return {
    Authorization: `Bearer ${API_KEY}`,
    "X-Workspace-ID": WORKSPACE_ID,
    "Content-Type": "application/json",
  };
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE_URL + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString(), {
    headers: headers(),
    next: { revalidate: 30 }, // cache for 30s then revalidate
  });
  if (!res.ok) throw new Error(`Lore API error ${res.status}: ${path}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE_URL + path, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Lore API error ${res.status}: ${text}`);
  }
  return res.json();
}

async function del(path: string): Promise<void> {
  const res = await fetch(BASE_URL + path, {
    method: "DELETE",
    headers: headers(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Lore API error ${res.status}: ${path}`);
}

// ─── Types ────────────────────────────────────────────────────────────────────

export type RuleStatus = "proposed" | "active" | "conflict" | "needs_review" | "archived";
export type RuleType = "prohibition" | "preference" | "requirement" | "pattern";

export interface Rule {
  id: string;
  content: string;
  rule_type: RuleType;
  status: RuleStatus;
  confidence: number;
  tool_scope: string[];
  context_scope: Record<string, string>;
  source_event_ids: string[];
  conflict_with: string[];
  last_supported: string | null;
  created_at: string;
  updated_at: string;
  workspace_id: string;
}

export interface Event {
  id: string;
  event_type: string;
  source_tool: string;
  actor_id: string | null;
  ai_output_id: string | null;
  summary: string | null;
  context_tags: string[];
  raw_payload: Record<string, unknown>;
  created_at: string;
  workspace_id: string;
}

export interface Entity {
  id: string;
  name: string;
  entity_type: string;
  known_facts: Record<string, unknown>;
  correction_count: number;
  last_seen: string | null;
  created_at: string;
  workspace_id: string;
}

export interface Proposal {
  id: string;
  content: string;
  rule_type: RuleType;
  confidence: number;
  tool_scope: string[];
  context_scope: Record<string, string>;
  source_event_ids: string[];
  status: "pending" | "confirmed" | "rejected";
  created_at: string;
  workspace_id: string;
}

export interface ApiKey {
  id: string;
  name: string;
  scopes: string[];
  created_by: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
  workspace_id: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ─── API Functions ────────────────────────────────────────────────────────────

export function isConfigured(): boolean {
  return Boolean(API_KEY);
}

export async function getHealth() {
  return get<{ status: string; version: string; timestamp: string }>("/v1/health");
}

export async function getRules(params?: { status?: RuleStatus; limit?: number; offset?: number }) {
  return get<{ rules: Rule[]; total: number }>("/v1/rules", params as Record<string, string | number | undefined>);
}

export async function getRule(id: string) {
  return get<Rule>(`/v1/rules/${id}`);
}

export async function getEvents(params?: { limit?: number; offset?: number; source_tool?: string }) {
  return get<{ events: Event[]; total: number }>("/v1/events", params as Record<string, string | number | undefined>);
}

export async function getEntities(params?: { limit?: number; offset?: number; entity_type?: string }) {
  return get<{ entities: Entity[]; total: number }>("/v1/entities", params as Record<string, string | number | undefined>);
}

export async function getProposals(params?: { limit?: number; offset?: number }) {
  return get<{ proposals: Proposal[]; total: number }>("/v1/proposals", params as Record<string, string | number | undefined>);
}

export async function confirmProposal(id: string) {
  return post<{ rule: Rule; conflicts_detected: boolean }>(`/v1/proposals/${id}/confirm`, {});
}

export async function rejectProposal(id: string) {
  return post<unknown>(`/v1/proposals/${id}/reject`, {});
}

export async function patchRule(id: string, body: Partial<Pick<Rule, "status" | "content" | "confidence">>) {
  const res = await fetch(`${BASE_URL}/v1/rules/${id}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Lore API error ${res.status}`);
  return res.json() as Promise<Rule>;
}

export async function deleteRule(id: string) {
  return del(`/v1/rules/${id}`);
}

export async function getApiKeys() {
  return get<{ api_keys: ApiKey[] }>("/v1/auth/api-keys");
}

export async function createApiKey(name: string, scopes: string[]) {
  return post<{ api_key: ApiKey; plaintext_key: string }>("/v1/auth/api-keys", { name, scopes });
}

export async function deleteApiKey(id: string) {
  return del(`/v1/auth/api-keys/${id}`);
}

export async function runMining() {
  return post<unknown>("/v1/mining/run", {});
}

export async function runExpireCheck() {
  return post<unknown>("/v1/mining/expire-check", {});
}
