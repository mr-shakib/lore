import { getEntities } from "@/lib/api";
import PageHeader from "@/components/page-header";
import { relativeTime, shortDate } from "@/lib/utils";
import { Network } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function EntitiesPage() {
  let entities: Awaited<ReturnType<typeof getEntities>>["entities"] = [];
  let total = 0;
  try {
    const res = await getEntities({ limit: 100 });
    entities = res.entities;
    total    = res.total;
  } catch { /* show empty state */ }

  // Group by type
  const byType: Record<string, typeof entities> = {};
  for (const e of entities) {
    if (!byType[e.entity_type]) byType[e.entity_type] = [];
    byType[e.entity_type].push(e);
  }

  const typeEntries = Object.entries(byType).sort((a, b) => b[1].length - a[1].length);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Entities"
        description={`${total} tracked entities in memory graph`}
      />

      {entities.length === 0 ? (
        <div className="text-center py-20">
          <Network className="w-8 h-8 text-text-faint mx-auto mb-3" strokeWidth={1} />
          <p className="text-sm text-text-muted">No entities tracked yet</p>
          <p className="text-xs text-text-faint mt-1">Entities are extracted from events automatically.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Type summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {typeEntries.slice(0, 4).map(([type, items]) => (
              <div key={type} className="rounded-md border border-border bg-surface-1 px-3 py-2.5">
                <span className="text-[11px] font-mono text-text-muted uppercase tracking-widest">{type}</span>
                <p className="text-2xl font-mono font-semibold text-text mt-1">{items.length}</p>
              </div>
            ))}
          </div>

          {/* Entities by type */}
          {typeEntries.map(([type, items]) => (
            <section key={type} className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-medium uppercase tracking-widest text-text-muted">{type}</span>
                <span className="text-[10px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded">{items.length}</span>
                <div className="flex-1 h-px bg-border" />
              </div>
              <div className="rounded-md border border-border bg-surface-1 divide-y divide-border">
                {items.map(entity => (
                  <EntityRow key={entity.id} entity={entity} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function EntityRow({ entity }: { entity: Awaited<ReturnType<typeof getEntities>>["entities"][0] }) {
  const factKeys = Object.keys(entity.known_facts ?? {});

  return (
    <div className="px-4 py-3 flex items-start gap-4">
      {/* Avatar */}
      <div className="w-8 h-8 rounded-sm bg-surface-3 border border-border flex items-center justify-center shrink-0">
        <span className="text-xs font-mono text-text-muted">
          {entity.name.slice(0, 2).toUpperCase()}
        </span>
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-text font-medium">{entity.name}</p>
          {entity.correction_count > 0 && (
            <span className="text-[10px] font-mono text-amber bg-amber/10 px-1.5 py-0.5 rounded border border-amber/20">
              {entity.correction_count} corrections
            </span>
          )}
        </div>
        {factKeys.length > 0 && (
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {factKeys.slice(0, 4).map(k => (
              <span key={k} className="text-[10px] font-mono text-text-faint">
                {k}: <span className="text-text-muted">{String(entity.known_facts[k]).slice(0, 30)}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Meta */}
      <div className="text-right shrink-0">
        <p className="text-[11px] text-text-faint">last seen</p>
        <p className="text-[11px] font-mono text-text-muted">{relativeTime(entity.last_seen)}</p>
      </div>
    </div>
  );
}
