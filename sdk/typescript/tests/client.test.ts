import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoreClient } from "../src/client.js";

// ---------- fetch mock helpers -----------------------------------------------

type FetchMock = ReturnType<typeof vi.fn>;

function mockFetchOk(body: unknown): FetchMock {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: () => Promise.resolve(body),
  });
}

function mockFetchStatus(status: number): FetchMock {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    headers: { get: () => null },
    json: () => Promise.resolve({ detail: "error" }),
  });
}

function mockFetchNetworkError(): FetchMock {
  return vi.fn().mockRejectedValue(new TypeError("fetch failed"));
}

function mockFetchAbort(): FetchMock {
  return vi.fn().mockRejectedValue(Object.assign(new Error("aborted"), { name: "AbortError" }));
}

// ---------- fixtures ---------------------------------------------------------

const RAW_CONTEXT = {
  context_id: "ctx_001",
  formatted_injection: "## Org Rules\n- always use metric units",
  rules: [{ id: "r1", content: "use metric units", confidence: 0.9 }],
  entities: [{ id: "e1", name: "Acme Corp", type: "org" }],
  decisions: [{ rule_id: "r1", applied: true }],
  cached: false,
};

const RAW_EVENT = { accepted: true, event_id: "evt_abc" };

function makeClient(): LoreClient {
  return new LoreClient({
    apiKey: "sk-lore-test1234",
    workspaceId: "ws_test",
    baseUrl: "https://lore-test.local",
  });
}

// ---------- constructor tests ------------------------------------------------

describe("LoreClient constructor", () => {
  it("throws when apiKey is missing", () => {
    expect(() => new LoreClient({ apiKey: "", workspaceId: "ws_1", baseUrl: "http://x" })).toThrow(
      "apiKey is required",
    );
  });

  it("throws when workspaceId is missing", () => {
    expect(
      () => new LoreClient({ apiKey: "sk-lore-abc", workspaceId: "", baseUrl: "http://x" }),
    ).toThrow("workspaceId is required");
  });

  it("constructs successfully with valid options", () => {
    expect(() => makeClient()).not.toThrow();
  });
});

// ---------- getContext -------------------------------------------------------

describe("LoreClient.getContext", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns mapped ContextResponse on success", async () => {
    vi.stubGlobal("fetch", mockFetchOk(RAW_CONTEXT));
    const ctx = await makeClient().getContext({ query: "PII policy", tool: "gpt-4o" });
    expect(ctx.isEmpty).toBe(false);
    expect(ctx.contextId).toBe("ctx_001");
    expect(ctx.formattedInjection).toContain("metric");
    expect(ctx.rules).toHaveLength(1);
    expect(ctx.entities).toHaveLength(1);
    expect(ctx.cached).toBe(false);
  });

  it("sends Authorization header", async () => {
    const fetchMock = mockFetchOk(RAW_CONTEXT);
    vi.stubGlobal("fetch", fetchMock);
    await makeClient().getContext({ query: "q", tool: "t" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer sk-lore-test1234",
    );
  });

  it("sends X-Workspace-ID header", async () => {
    const fetchMock = mockFetchOk(RAW_CONTEXT);
    vi.stubGlobal("fetch", fetchMock);
    await makeClient().getContext({ query: "q", tool: "t" });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-Workspace-ID"]).toBe("ws_test");
  });

  it("returns emptyContext on 401", async () => {
    vi.stubGlobal("fetch", mockFetchStatus(401));
    const ctx = await makeClient().getContext({ query: "q", tool: "t" });
    expect(ctx.isEmpty).toBe(true);
    expect(ctx.formattedInjection).toBe("");
  });

  it("returns emptyContext on network error", async () => {
    vi.stubGlobal("fetch", mockFetchNetworkError());
    const ctx = await makeClient().getContext({ query: "q", tool: "t" });
    expect(ctx.isEmpty).toBe(true);
  });

  it("returns emptyContext on timeout", async () => {
    vi.stubGlobal("fetch", mockFetchAbort());
    const ctx = await makeClient().getContext({ query: "q", tool: "t" });
    expect(ctx.isEmpty).toBe(true);
  });

  it("retries 3 times on 500 then returns empty", async () => {
    const fetchMock = mockFetchStatus(500);
    vi.stubGlobal("fetch", fetchMock);
    // Fast-forward timers so retries don't actually wait
    vi.useFakeTimers();
    const promise = makeClient().getContext({ query: "q", tool: "t" });
    // Advance timers through all backoff delays
    for (let i = 0; i < 5; i++) await vi.runAllTimersAsync();
    const ctx = await promise;
    vi.useRealTimers();
    expect(ctx.isEmpty).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});

// ---------- reportCorrection -------------------------------------------------

describe("LoreClient.reportCorrection", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns accepted result on success", async () => {
    vi.stubGlobal("fetch", mockFetchOk(RAW_EVENT));
    const result = await makeClient().reportCorrection({
      aiOutputId: "out_1",
      summary: "AI used imperial units",
      tool: "gpt-4o",
    });
    expect(result.accepted).toBe(true);
    expect(result.eventId).toBe("evt_abc");
  });

  it("sends event_type=correction", async () => {
    const fetchMock = mockFetchOk(RAW_EVENT);
    vi.stubGlobal("fetch", fetchMock);
    await makeClient().reportCorrection({
      aiOutputId: "out_1",
      summary: "wrong",
      tool: "gpt-4o",
    });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.event_type).toBe("correction");
    expect(body.ai_output_id).toBe("out_1");
  });

  it("returns notAccepted on network error", async () => {
    vi.stubGlobal("fetch", mockFetchNetworkError());
    const result = await makeClient().reportCorrection({
      aiOutputId: "out_1",
      summary: "correction",
      tool: "gpt-4o",
    });
    expect(result.accepted).toBe(false);
    expect(result.eventId).toBeNull();
  });
});

// ---------- reportOutput -----------------------------------------------------

describe("LoreClient.reportOutput", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns accepted result on success", async () => {
    vi.stubGlobal("fetch", mockFetchOk(RAW_EVENT));
    const result = await makeClient().reportOutput({ outputId: "out_2", tool: "claude-3" });
    expect(result.accepted).toBe(true);
    expect(result.eventId).toBe("evt_abc");
  });

  it("sends event_type=approval", async () => {
    const fetchMock = mockFetchOk(RAW_EVENT);
    vi.stubGlobal("fetch", fetchMock);
    await makeClient().reportOutput({ outputId: "out_2", tool: "claude-3" });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.event_type).toBe("approval");
    expect(body.output_id).toBe("out_2");
  });

  it("returns notAccepted on server error", async () => {
    vi.stubGlobal("fetch", mockFetchStatus(503));
    const result = await makeClient().reportOutput({ outputId: "out_2", tool: "claude-3" });
    expect(result.accepted).toBe(false);
  });
});
