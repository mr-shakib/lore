/**
 * Fetch-based HTTP transport with retry + exponential backoff.
 * Uses the global `fetch` available in Node 18+ and all modern browsers.
 * Internal module — not part of public API.
 */

import {
  AuthError,
  LoreAiError,
  NetworkError,
  RateLimitError,
  ServerError,
  TimeoutError,
} from "./errors.js";

const MAX_RETRIES = 3;
const BACKOFF_BASE_MS = 500;
const CONTEXT_TIMEOUT_MS = 5_000;
const WRITE_TIMEOUT_MS = 10_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function classify(status: number, retryAfterHeader?: string | null): LoreAiError {
  if (status === 401 || status === 403) return new AuthError();
  if (status === 429) {
    const ms = retryAfterHeader ? parseInt(retryAfterHeader, 10) * 1000 : undefined;
    return new RateLimitError(ms);
  }
  return new ServerError(status);
}

function isRetryable(err: unknown): boolean {
  return err instanceof NetworkError || err instanceof ServerError;
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...init, signal: controller.signal });
    clearTimeout(timer);
    return res;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") throw new TimeoutError();
    throw new NetworkError(err);
  }
}

async function requestWithRetry<T>(
  url: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<T> {
  let lastErr: LoreAiError = new NetworkError();
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      await sleep(BACKOFF_BASE_MS * Math.pow(2, attempt - 1));
    }
    try {
      const res = await fetchWithTimeout(url, init, timeoutMs);
      if (!res.ok) {
        const err = classify(res.status, res.headers.get("retry-after"));
        if (!isRetryable(err)) throw err;          // non-retryable — throw immediately
        lastErr = err;
        continue;
      }
      return (await res.json()) as T;
    } catch (err) {
      if (err instanceof LoreAiError && !isRetryable(err)) throw err;
      lastErr = err instanceof LoreAiError ? err : new NetworkError(err);
    }
  }
  throw lastErr;
}

export interface TransportOptions {
  baseUrl: string;
  apiKey: string;
  workspaceId: string;
}

export class Transport {
  private headers: Record<string, string>;
  private baseUrl: string;

  constructor(opts: TransportOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, "");
    this.headers = {
      Authorization: `Bearer ${opts.apiKey}`,
      "X-Workspace-ID": opts.workspaceId,
      "Content-Type": "application/json",
      "User-Agent": "@lore-ai/sdk/0.1.0",
    };
  }

  async get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    const url = new URL(this.baseUrl + path);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) {
          if (Array.isArray(v)) {
            v.forEach((item) => url.searchParams.append(k, String(item)));
          } else {
            url.searchParams.set(k, String(v));
          }
        }
      }
    }
    return requestWithRetry<T>(url.toString(), { method: "GET", headers: this.headers }, CONTEXT_TIMEOUT_MS);
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const url = this.baseUrl + path;
    return requestWithRetry<T>(
      url,
      { method: "POST", headers: this.headers, body: JSON.stringify(body) },
      WRITE_TIMEOUT_MS,
    );
  }
}
