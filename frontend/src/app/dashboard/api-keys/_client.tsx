"use client";

import { useState } from "react";
import { KeyRound, Plus, Trash2, Copy, Check, Eye, EyeOff } from "lucide-react";

interface ApiKey {
  id: string;
  name: string;
  scopes: string[];
  created_by: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

interface ApiKeyData {
  keys: ApiKey[];
  newKey?: { key: ApiKey; plaintext: string };
  error?: string;
}

// Server actions are colocated in the server page wrapper below
export default function ApiKeysClientPage({ data }: { data: ApiKeyData }) {
  const [copied, setCopied] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);

  function copyToClipboard(text: string, id: string) {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  }

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

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-text tracking-tight">API Keys</h1>
          <p className="text-sm text-text-muted mt-0.5">Manage authentication keys for SDK and integrations</p>
        </div>
      </div>

      {/* New key revealed */}
      {data.newKey && (
        <div className="rounded-md border border-green-lore/30 bg-green-lore/5 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-green-lore" />
            <p className="text-sm font-medium text-green-lore">
              Key created: <span className="font-mono">{data.newKey.key.name}</span>
            </p>
          </div>
          <p className="text-xs text-text-muted">Copy this key now — it will not be shown again.</p>
          <div className="flex items-center gap-2">
            <div className="flex-1 font-mono text-sm text-text bg-surface border border-border rounded px-3 py-2 truncate">
              {showKey ? data.newKey.plaintext : "sk-lore-••••••••••••••••••••••••••••••••"}
            </div>
            <button
              onClick={() => setShowKey(v => !v)}
              className="p-2 rounded border border-border bg-surface-1 hover:bg-surface-2 transition-colors text-text-muted"
            >
              {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
            <button
              onClick={() => copyToClipboard(data.newKey!.plaintext, "new")}
              className="flex items-center gap-1.5 px-3 py-2 rounded border border-green-lore/30 bg-green-lore/10 text-green-lore text-xs hover:bg-green-lore/20 transition-colors"
            >
              {copied === "new" ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied === "new" ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {/* Create form */}
      <CreateKeyForm />

      {/* Keys table */}
      <div className="rounded-md border border-border bg-surface-1">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Active Keys</span>
          <span className="text-xs font-mono text-text-faint">{data.keys.length} keys</span>
        </div>
        {data.keys.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <KeyRound className="w-7 h-7 text-text-faint mx-auto mb-3" strokeWidth={1} />
            <p className="text-sm text-text-muted">No API keys yet</p>
            <p className="text-xs text-text-faint mt-1">Create a key to authenticate the SDK and integrations.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {data.keys.map(key => (
              <div key={key.id} className="px-4 py-3 flex items-center gap-4 group">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text font-medium">{key.name}</p>
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    <span className="text-[11px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded">
                      {key.id.slice(0, 12)}…
                    </span>
                    {key.scopes.map(scope => (
                      <span key={scope} className="text-[10px] font-mono text-blue-lore bg-blue-lore/10 px-1.5 py-0.5 rounded border border-blue-lore/20">
                        {scope}
                      </span>
                    ))}
                    <span className="text-[11px] text-text-faint">
                      last used: {relTime(key.last_used_at)}
                    </span>
                    <span className="text-[11px] text-text-faint">
                      created: {relTime(key.created_at)}
                    </span>
                  </div>
                </div>
                <DeleteKeyForm keyId={key.id} keyName={key.name} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CreateKeyForm() {
  return (
    <form method="POST" className="rounded-md border border-border bg-surface-1 p-4">
      <p className="text-sm font-medium text-text mb-3">Create New Key</p>
      <div className="flex items-end gap-3">
        <div className="flex-1 space-y-1">
          <label className="text-xs text-text-muted">Name</label>
          <input
            name="name"
            type="text"
            placeholder="e.g. production-agent"
            required
            className="w-full px-3 py-2 text-sm bg-surface border border-border rounded text-text placeholder:text-text-faint focus:outline-none focus:border-amber/50 focus:ring-1 focus:ring-amber/20 transition-colors"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-text-muted">Scopes</label>
          <select
            name="scopes"
            className="px-3 py-2 text-sm bg-surface border border-border rounded text-text focus:outline-none focus:border-amber/50 transition-colors"
          >
            <option value="read,write">read + write</option>
            <option value="read">read only</option>
          </select>
        </div>
        <input type="hidden" name="_action" value="create" />
        <button
          type="submit"
          className="flex items-center gap-1.5 px-4 py-2 text-sm bg-amber text-surface font-medium rounded hover:bg-amber-bright transition-colors"
        >
          <Plus className="w-4 h-4" /> Create
        </button>
      </div>
    </form>
  );
}

function DeleteKeyForm({ keyId, keyName }: { keyId: string; keyName: string }) {
  return (
    <form method="POST" className="opacity-0 group-hover:opacity-100 transition-opacity">
      <input type="hidden" name="_action" value="delete" />
      <input type="hidden" name="id" value={keyId} />
      <button
        type="submit"
        onClick={e => {
          if (!confirm(`Revoke key "${keyName}"? This cannot be undone.`)) e.preventDefault();
        }}
        className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] text-red-lore bg-red-lore/10 border border-red-lore/20 rounded hover:bg-red-lore/20 transition-colors"
      >
        <Trash2 className="w-3 h-3" /> Revoke
      </button>
    </form>
  );
}
