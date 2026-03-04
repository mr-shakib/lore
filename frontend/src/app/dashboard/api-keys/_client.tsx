"use client";

import { useActionState, useState } from "react";
import { KeyRound, Plus, Trash2, Copy, Check, Eye, EyeOff, Terminal, ChevronDown, ChevronUp } from "lucide-react";
import { createKeyAction, deleteKeyAction, type CreateKeyState } from "./actions";
import type { ApiKey } from "@/lib/api";

interface ApiKeysClientPageProps {
  initialKeys: ApiKey[];
  workspaceId: string | null;
  deleteAction: typeof deleteKeyAction;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function relTime(date: string | null): string {
  if (!date) return "never";
  try {
    const d = new Date(date);
    const diff = Date.now() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch { return "—"; }
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ApiKeysClientPage({ initialKeys, workspaceId, deleteAction }: ApiKeysClientPageProps) {
  const [state, formAction, isPending] = useActionState<CreateKeyState | null, FormData>(createKeyAction, null);
  const [copied, setCopied] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [showSnippet, setShowSnippet] = useState(false);

  // Prefer workspace_id from a freshly-created key, then fall back to list
  const displayWorkspaceId = state?.created?.workspace_id ?? workspaceId;
  const newKey = state?.created ?? null;

  function copy(text: string, id: string) {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold text-text tracking-tight">API Keys</h1>
        <p className="text-sm text-text-muted mt-0.5">
          Manage authentication credentials for the SDK and integrations
        </p>
      </div>

      {/* Workspace ID — shown as soon as it's known */}
      {displayWorkspaceId && (
        <div className="rounded-md border border-border bg-surface-1 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Workspace ID</span>
            <span className="text-[10px] text-text-faint">Required for SDK initialization</span>
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-sm text-amber bg-surface px-3 py-2 rounded border border-border truncate">
              {displayWorkspaceId}
            </code>
            <button
              onClick={() => copy(displayWorkspaceId, "ws")}
              className="flex items-center gap-1.5 px-3 py-2 rounded border border-border bg-surface hover:bg-surface-2 text-text-muted hover:text-text text-xs transition-colors shrink-0"
            >
              {copied === "ws" ? <Check className="w-3.5 h-3.5 text-green-lore" /> : <Copy className="w-3.5 h-3.5" />}
              {copied === "ws" ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {/* New key reveal — shown immediately after creation */}
      {newKey && (
        <div className="rounded-md border border-green-lore/30 bg-green-lore/5 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-green-lore animate-pulse" />
            <p className="text-sm font-medium text-green-lore">
              Key created: <span className="font-mono">{newKey.name}</span>
            </p>
          </div>
          <p className="text-xs text-text-muted">
            Copy this key now — it will <span className="text-text font-medium">not be shown again</span>.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-sm text-text bg-surface border border-green-lore/20 rounded px-3 py-2 truncate">
              {showKey ? newKey.plaintext : "sk-lore-" + "•".repeat(32)}
            </code>
            <button
              onClick={() => setShowKey(v => !v)}
              className="p-2 rounded border border-border bg-surface hover:bg-surface-2 transition-colors text-text-muted shrink-0"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
            <button
              onClick={() => copy(newKey.plaintext, "new")}
              className="flex items-center gap-1.5 px-3 py-2 rounded border border-green-lore/30 bg-green-lore/10 text-green-lore text-xs hover:bg-green-lore/20 transition-colors shrink-0"
            >
              {copied === "new" ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied === "new" ? "Copied" : "Copy"}
            </button>
          </div>

          {/* Inline quick-start snippet */}
          <div>
            <button
              onClick={() => setShowSnippet(v => !v)}
              className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text transition-colors mt-1"
            >
              <Terminal className="w-3.5 h-3.5" />
              Quick start
              {showSnippet ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
            {showSnippet && (
              <pre className="mt-2 text-xs font-mono text-amber/90 bg-surface border border-border px-4 py-3 rounded-md overflow-x-auto leading-relaxed">
{`pip install loremem

from loremem import LoreClient

lore = LoreClient(
    api_key="${newKey.plaintext}",
    workspace_id="${newKey.workspace_id}",
)

lore.capture(
    event_type="correction",
    actor_id="user@example.com",
    summary="AI recommended the wrong approach",
    source_tool="your-ai-tool",
)`}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Error state */}
      {state?.error && (
        <div className="rounded-md border border-red-lore/30 bg-red-lore/5 px-4 py-3 text-sm text-red-lore">
          {state.error}
        </div>
      )}

      {/* Create form */}
      <form action={formAction} className="rounded-md border border-border bg-surface-1 p-4">
        <p className="text-sm font-medium text-text mb-3">Create New Key</p>
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-48 space-y-1">
            <label htmlFor="key-name" className="text-xs text-text-muted">Name</label>
            <input
              id="key-name"
              name="name"
              type="text"
              placeholder="e.g. production-agent"
              required
              className="w-full px-3 py-2 text-sm bg-surface border border-border rounded text-text placeholder:text-text-faint focus:outline-none focus:border-amber/50 focus:ring-1 focus:ring-amber/20 transition-colors"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="key-scopes" className="text-xs text-text-muted">Scopes</label>
            <select
              id="key-scopes"
              name="scopes"
              className="px-3 py-2 text-sm bg-surface border border-border rounded text-text focus:outline-none focus:border-amber/50 transition-colors"
            >
              <option value="read,write">read + write</option>
              <option value="read">read only</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={isPending}
            className="flex items-center gap-1.5 px-4 py-2 text-sm bg-amber text-surface font-medium rounded hover:bg-amber-bright transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="w-4 h-4" />
            {isPending ? "Creating…" : "Create"}
          </button>
        </div>
      </form>

      {/* Keys list */}
      <div className="rounded-md border border-border bg-surface-1">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Active Keys</span>
          <span className="text-xs font-mono text-text-faint">{initialKeys.length} keys</span>
        </div>
        {initialKeys.length === 0 ? (
          <div className="px-4 py-14 text-center">
            <KeyRound className="w-7 h-7 text-text-faint mx-auto mb-3" strokeWidth={1} />
            <p className="text-sm text-text-muted">No keys yet</p>
            <p className="text-xs text-text-faint mt-1">Create a key above to authenticate the SDK.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {initialKeys.map(key => (
              <KeyRow
                key={key.id}
                apiKey={key}
                deleteAction={deleteAction}
                onCopy={copy}
                copied={copied}
              />
            ))}
          </div>
        )}
      </div>

      {/* SDK guide — shown once the user has at least one key */}
      {initialKeys.length > 0 && displayWorkspaceId && (
        <SdkGuide workspaceId={displayWorkspaceId} onCopy={copy} copied={copied} />
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KeyRow({
  apiKey,
  deleteAction,
  onCopy,
  copied,
}: {
  apiKey: ApiKey;
  deleteAction: typeof deleteKeyAction;
  onCopy: (text: string, id: string) => void;
  copied: string | null;
}) {
  return (
    <div className="px-4 py-3 flex items-center gap-4 group hover:bg-surface-2 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text font-medium">{apiKey.name}</p>
        <div className="flex items-center gap-2.5 mt-1 flex-wrap">
          <button
            onClick={() => onCopy(apiKey.id, `id-${apiKey.id}`)}
            className="inline-flex items-center gap-1 text-[11px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded hover:text-text-muted transition-colors"
          >
            {copied === `id-${apiKey.id}` ? <Check className="w-2.5 h-2.5 text-green-lore" /> : null}
            {apiKey.id.slice(0, 16)}…
          </button>
          {apiKey.scopes.map(scope => (
            <span
              key={scope}
              className="text-[10px] font-mono text-blue-lore bg-blue-lore/10 px-1.5 py-0.5 rounded border border-blue-lore/20"
            >
              {scope}
            </span>
          ))}
          <span className="text-[11px] text-text-faint">last used: {relTime(apiKey.last_used_at)}</span>
          <span className="text-[11px] text-text-faint">created: {relTime(apiKey.created_at)}</span>
        </div>
      </div>
      <form action={deleteAction} className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
        <input type="hidden" name="id" value={apiKey.id} />
        <button
          type="submit"
          onClick={e => {
            if (!confirm(`Revoke "${apiKey.name}"? This cannot be undone.`)) e.preventDefault();
          }}
          className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] text-red-lore bg-red-lore/10 border border-red-lore/20 rounded hover:bg-red-lore/20 transition-colors"
        >
          <Trash2 className="w-3 h-3" /> Revoke
        </button>
      </form>
    </div>
  );
}

function SdkGuide({
  workspaceId,
  onCopy,
  copied,
}: {
  workspaceId: string;
  onCopy: (text: string, id: string) => void;
  copied: string | null;
}) {
  const pythonSnippet =
`pip install loremem

from loremem import LoreClient

lore = LoreClient(
    api_key="sk-lore-...",      # your key above
    workspace_id="${workspaceId}",
)

lore.capture(
    event_type="correction",
    actor_id="user@example.com",
    summary="AI recommended the wrong approach",
    source_tool="your-ai-tool",
)`;

  const tsSnippet =
`npm install @lore-ai/sdk

import { LoreClient } from "@lore-ai/sdk";

const lore = new LoreClient({
  apiKey: "sk-lore-...",        // your key above
  workspaceId: "${workspaceId}",
});

await lore.capture({
  eventType: "correction",
  actorId: "user@example.com",
  summary: "AI recommended the wrong approach",
  sourceTool: "your-ai-tool",
});`;

  return (
    <div className="rounded-md border border-border bg-surface-1">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <Terminal className="w-4 h-4 text-text-faint" strokeWidth={1.5} />
        <h2 className="text-sm font-medium text-text">SDK Quick Start</h2>
      </div>
      <div className="p-4 space-y-4">
        <SnippetBlock label="Python" snippetId="py" code={pythonSnippet} onCopy={onCopy} copied={copied} />
        <SnippetBlock label="TypeScript" snippetId="ts" code={tsSnippet} onCopy={onCopy} copied={copied} />
      </div>
    </div>
  );
}

function SnippetBlock({
  label,
  snippetId,
  code,
  onCopy,
  copied,
}: {
  label: string;
  snippetId: string;
  code: string;
  onCopy: (text: string, id: string) => void;
  copied: string | null;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-mono text-text-muted">{label}</span>
        <button
          onClick={() => onCopy(code, snippetId)}
          className="flex items-center gap-1 text-[11px] text-text-faint hover:text-text-muted transition-colors"
        >
          {copied === snippetId ? (
            <Check className="w-3 h-3 text-green-lore" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
          {copied === snippetId ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="text-xs font-mono text-amber/90 bg-surface border border-border px-4 py-3 rounded overflow-x-auto leading-relaxed">
        {code}
      </pre>
    </div>
  );
}
