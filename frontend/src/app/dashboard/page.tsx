import { getRules, getEvents, getEntities, getProposals, isConfigured } from "@/lib/api";
import StatsCard from "@/components/stats-card";
import StatusBadge from "@/components/status-badge";
import { ShieldCheck, MessageSquareWarning, Network, Lightbulb, AlertTriangle, Clock } from "lucide-react";
import { relativeTime, truncate, confidencePct } from "@/lib/utils";
import Link from "next/link";

export const dynamic = "force-dynamic";

async function fetchDashboardData() {
  if (!isConfigured()) return null;
  try {
    const [rulesRes, eventsRes, entitiesRes, proposalsRes] = await Promise.allSettled([
      getRules({ limit: 100 }),
      getEvents({ limit: 20 }),
      getEntities({ limit: 100 }),
      getProposals({ limit: 10 }),
    ]);
    return {
      rules:     rulesRes.status     === "fulfilled" ? rulesRes.value     : null,
      events:    eventsRes.status    === "fulfilled" ? eventsRes.value    : null,
      entities:  entitiesRes.status  === "fulfilled" ? entitiesRes.value  : null,
      proposals: proposalsRes.status === "fulfilled" ? proposalsRes.value : null,
    };
  } catch {
    return null;
  }
}

export default async function DashboardPage() {
  if (!isConfigured()) {
    return <SetupRequired />;
  }

  const data = await fetchDashboardData();

  const rules     = data?.rules?.rules     ?? [];
  const events    = data?.events?.events   ?? [];
  const entities  = data?.entities?.entities ?? [];
  const proposals = data?.proposals?.proposals ?? [];

  const activeRules    = rules.filter(r => r.status === "active").length;
  const conflictRules  = rules.filter(r => r.status === "conflict").length;
  const reviewRules    = rules.filter(r => r.status === "needs_review").length;
  const pendingProposals = proposals.filter(p => p.status === "pending").length;

  const correctionEvents = events.filter(e => e.event_type === "correction");

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text tracking-tight">Overview</h1>
          <p className="text-sm text-text-muted mt-0.5">Workspace memory snapshot</p>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-green-lore animate-pulse" />
          <span className="text-xs text-text-muted font-mono">live</span>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          label="Active Rules"
          value={activeRules}
          sub={`${rules.length} total rules`}
          Icon={ShieldCheck}
          accent="green"
        />
        <StatsCard
          label="Events Captured"
          value={data?.events?.total ?? 0}
          sub={`${correctionEvents.length} corrections`}
          Icon={MessageSquareWarning}
          accent="amber"
        />
        <StatsCard
          label="Entities Tracked"
          value={data?.entities?.total ?? 0}
          sub="in memory graph"
          Icon={Network}
          accent="blue"
        />
        <StatsCard
          label="Pending Proposals"
          value={pendingProposals}
          sub="awaiting review"
          Icon={Lightbulb}
          accent={pendingProposals > 0 ? "amber" : "default"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent corrections */}
        <div className="lg:col-span-2 rounded-md border border-border bg-surface-1">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-text">Recent Corrections</h2>
            <Link href="/dashboard/corrections" className="text-xs text-amber hover:text-amber-bright transition-colors">
              View all →
            </Link>
          </div>
          <div className="divide-y divide-border">
            {events.length === 0 ? (
              <EmptyState label="No events captured yet" hint="Events appear when AI tools are integrated via SDK or webhooks." />
            ) : (
              events.slice(0, 8).map(event => (
                <div key={event.id} className="px-4 py-3 flex items-start gap-3">
                  <div className={`mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 ${event.event_type === "correction" ? "bg-amber" : "bg-green-lore"}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text truncate">{truncate(event.summary ?? event.event_type, 80)}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] font-mono text-text-faint">{event.source_tool}</span>
                      <span className="text-[11px] text-text-faint">·</span>
                      <span className="text-[11px] text-text-faint">{relativeTime(event.created_at)}</span>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded shrink-0">
                    {event.event_type}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Rules health */}
          <div className="rounded-md border border-border bg-surface-1">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-sm font-medium text-text">Rules Health</h2>
            </div>
            <div className="px-4 py-3 space-y-3">
              <RuleHealthRow label="Active" count={activeRules} total={rules.length} color="bg-green-lore" />
              <RuleHealthRow label="Proposed" count={rules.filter(r => r.status === "proposed").length} total={rules.length} color="bg-blue-lore" />
              <RuleHealthRow label="Needs Review" count={reviewRules} total={rules.length} color="bg-amber" />
              <RuleHealthRow label="Conflict" count={conflictRules} total={rules.length} color="bg-red-lore" />
            </div>
          </div>

          {/* Proposals */}
          {pendingProposals > 0 && (
            <div className="rounded-md border border-amber/20 bg-amber/5">
              <div className="px-4 py-3 border-b border-amber/20 flex items-center gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber" />
                <h2 className="text-sm font-medium text-amber">{pendingProposals} Proposals Pending</h2>
              </div>
              <div className="divide-y divide-amber/10">
                {proposals.filter(p => p.status === "pending").slice(0, 4).map(p => (
                  <div key={p.id} className="px-4 py-2.5">
                    <p className="text-xs text-text leading-relaxed">{truncate(p.content, 90)}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] font-mono text-amber/70">{confidencePct(p.confidence)}</span>
                      <span className="text-[10px] text-text-faint">confidence</span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="px-4 py-2 border-t border-amber/10">
                <Link href="/dashboard/rules?tab=proposals" className="text-xs text-amber hover:text-amber-bright transition-colors">
                  Review proposals →
                </Link>
              </div>
            </div>
          )}

          {/* Recent entities */}
          <div className="rounded-md border border-border bg-surface-1">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h2 className="text-sm font-medium text-text">Top Entities</h2>
              <Link href="/dashboard/entities" className="text-xs text-amber hover:text-amber-bright transition-colors">
                View all →
              </Link>
            </div>
            <div className="divide-y divide-border">
              {entities.length === 0 ? (
                <div className="px-4 py-6 text-center text-xs text-text-muted">No entities yet</div>
              ) : (
                entities.slice(0, 5).map(entity => (
                  <div key={entity.id} className="px-4 py-2.5 flex items-center gap-3">
                    <div className="w-7 h-7 rounded-sm bg-surface-3 flex items-center justify-center shrink-0">
                      <span className="text-[11px] font-mono text-text-muted">
                        {entity.name.slice(0, 2).toUpperCase()}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-text truncate">{entity.name}</p>
                      <p className="text-[10px] text-text-faint font-mono">{entity.entity_type}</p>
                    </div>
                    {entity.correction_count > 0 && (
                      <span className="text-[10px] font-mono text-text-faint">{entity.correction_count}×</span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Last seen */}
          <div className="rounded-md border border-border bg-surface-1 px-4 py-3 flex items-center gap-3">
            <Clock className="w-4 h-4 text-text-faint" strokeWidth={1.5} />
            <div>
              <p className="text-xs text-text-muted">Last event</p>
              <p className="text-xs text-text font-mono">
                {events.length > 0 ? relativeTime(events[0].created_at) : "none"}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function RuleHealthRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-muted">{label}</span>
        <span className="text-xs font-mono text-text">{count}</span>
      </div>
      <div className="h-1 bg-surface-3 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function EmptyState({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="text-sm text-text-muted">{label}</p>
      {hint && <p className="text-xs text-text-faint mt-1 max-w-xs mx-auto">{hint}</p>}
    </div>
  );
}

function SetupRequired() {
  return (
    <div className="max-w-xl mx-auto mt-20 space-y-6">
      <div className="text-center space-y-2">
        <div className="w-10 h-10 rounded-md bg-amber/10 border border-amber/20 flex items-center justify-center mx-auto">
          <AlertTriangle className="w-5 h-5 text-amber" />
        </div>
        <h1 className="text-lg font-semibold text-text">API Key Required</h1>
        <p className="text-sm text-text-muted">Set <code className="font-mono text-amber bg-amber/10 px-1.5 py-0.5 rounded">LORE_API_KEY</code> in <code className="font-mono text-text-muted bg-surface-2 px-1.5 py-0.5 rounded">.env.local</code> to connect the dashboard to your backend.</p>
      </div>
      <div className="rounded-md border border-border bg-surface-1 p-4 space-y-3">
        <p className="text-xs text-text-muted font-mono uppercase tracking-widest">Setup (one-time)</p>
        <pre className="text-xs font-mono text-amber bg-surface p-3 rounded border border-border overflow-x-auto">{`curl -X POST https://lore-m0st.onrender.com/v1/auth/api-keys \\
  -H "Authorization: Bearer <any-key>" \\
  -H "Content-Type: application/json" \\
  -d '{"name": "dashboard", "scopes": ["read", "write"]}'`}</pre>
        <p className="text-xs text-text-faint">Copy the <code className="font-mono">plaintext_key</code> from the response and set it as <code className="font-mono">LORE_API_KEY</code> in your <code className="font-mono">.env.local</code>.</p>
      </div>
    </div>
  );
}
