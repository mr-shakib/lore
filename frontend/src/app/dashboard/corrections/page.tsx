import { getEvents } from "@/lib/api";
import PageHeader from "@/components/page-header";
import { relativeTime, truncate } from "@/lib/utils";
import { MessageSquareWarning, Zap } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function CorrectionsPage() {
  let events: Awaited<ReturnType<typeof getEvents>>["events"] = [];
  let total = 0;
  try {
    const res = await getEvents({ limit: 100 });
    events = res.events;
    total  = res.total;
  } catch { /* show empty state */ }

  const corrections = events.filter(e => e.event_type === "correction");
  const approvals   = events.filter(e => e.event_type === "approval");
  const other       = events.filter(e => e.event_type !== "correction" && e.event_type !== "approval");

  return (
    <div className="space-y-8">
      <PageHeader
        title="Corrections"
        description={`${total} events total · ${corrections.length} corrections · ${approvals.length} approvals`}
      />

      {events.length === 0 ? (
        <div className="text-center py-20">
          <MessageSquareWarning className="w-8 h-8 text-text-faint mx-auto mb-3" strokeWidth={1} />
          <p className="text-sm text-text-muted">No events captured yet</p>
          <p className="text-xs text-text-faint mt-1 max-w-sm mx-auto">
            Integrate the Lore SDK into your AI agents and events will appear here.
          </p>
          <p className="mt-4 text-xs text-text-faint">
            Get your credentials from the{" "}
            <a href="/dashboard/api-keys" className="text-amber hover:text-amber-bright underline underline-offset-2 transition-colors">
              API Keys page
            </a>
            , then integrate the SDK.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Tool breakdown */}
          <ToolBreakdown events={events} />

          {/* Event stream */}
          <div className="rounded-md border border-border bg-surface-1 divide-y divide-border">
            <div className="px-4 py-3 flex items-center justify-between">
              <span className="text-xs font-mono text-text-muted uppercase tracking-widest">Event Stream</span>
              <span className="text-xs font-mono text-text-faint">{events.length} shown</span>
            </div>
            {events.map(event => (
              <EventRow key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EventRow({ event }: { event: Awaited<ReturnType<typeof getEvents>>["events"][0] }) {
  const isCorrection = event.event_type === "correction";
  const isApproval   = event.event_type === "approval";

  return (
    <div className="px-4 py-3 flex items-start gap-4 hover:bg-surface-2 transition-colors">
      {/* Type indicator */}
      <div className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
        isCorrection ? "bg-amber" : isApproval ? "bg-green-lore" : "bg-text-faint"
      }`} />

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text leading-relaxed">
          {event.summary ?? `${event.event_type} event`}
        </p>
        <div className="flex items-center gap-3 mt-1 flex-wrap">
          <span className="text-[11px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded">
            {event.source_tool}
          </span>
          {event.actor_id && (
            <span className="text-[11px] text-text-faint truncate max-w-[200px]">by {event.actor_id}</span>
          )}
          {event.context_tags.length > 0 && event.context_tags.slice(0, 3).map(tag => (
            <span key={tag} className="text-[10px] font-mono text-text-faint bg-surface-3 px-1.5 py-0.5 rounded">
              {tag}
            </span>
          ))}
          <span className="text-[11px] text-text-faint">{relativeTime(event.created_at)}</span>
        </div>
      </div>

      {/* Event type badge */}
      <span className={`text-[10px] font-mono px-2 py-0.5 rounded shrink-0 ${
        isCorrection ? "bg-amber/10 text-amber border border-amber/20" :
        isApproval   ? "bg-green-lore/10 text-green-lore border border-green-lore/20" :
                       "bg-surface-2 text-text-faint border border-border"
      }`}>
        {event.event_type}
      </span>
    </div>
  );
}

function ToolBreakdown({ events }: { events: Awaited<ReturnType<typeof getEvents>>["events"] }) {
  const byTool: Record<string, number> = {};
  for (const e of events) {
    byTool[e.source_tool] = (byTool[e.source_tool] ?? 0) + 1;
  }
  const sorted = Object.entries(byTool).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {sorted.slice(0, 4).map(([tool, count]) => (
        <div key={tool} className="rounded-md border border-border bg-surface-1 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-text-faint" strokeWidth={1.5} />
            <span className="text-xs font-mono text-text-muted truncate">{tool}</span>
          </div>
          <p className="text-2xl font-mono font-semibold text-text mt-1">{count}</p>
        </div>
      ))}
    </div>
  );
}
