import { getRules, getProposals, confirmProposal, rejectProposal, patchRule, deleteRule } from "@/lib/api";
import StatusBadge from "@/components/status-badge";
import PageHeader from "@/components/page-header";
import { relativeTime, confidencePct, truncate } from "@/lib/utils";
import { revalidatePath } from "next/cache";
import { ShieldCheck, Trash2, CheckCircle, XCircle, BookOpen } from "lucide-react";

export const dynamic = "force-dynamic";

async function confirmAction(id: string) {
  "use server";
  await confirmProposal(id);
  revalidatePath("/dashboard/rules");
}

async function rejectAction(id: string) {
  "use server";
  await rejectProposal(id);
  revalidatePath("/dashboard/rules");
}

async function archiveAction(id: string) {
  "use server";
  await patchRule(id, { status: "archived" });
  revalidatePath("/dashboard/rules");
}

async function activateAction(id: string) {
  "use server";
  await patchRule(id, { status: "active" });
  revalidatePath("/dashboard/rules");
}

export default async function RulesPage() {
  const [rulesRes, proposalsRes] = await Promise.allSettled([
    getRules({ limit: 100 }),
    getProposals({ limit: 50 }),
  ]);

  const rules     = rulesRes.status     === "fulfilled" ? rulesRes.value.rules         : [];
  const proposals = proposalsRes.status === "fulfilled" ? proposalsRes.value.proposals : [];

  const pendingProposals = proposals.filter(p => p.status === "pending");
  const activeRules      = rules.filter(r => r.status === "active");
  const reviewRules      = rules.filter(r => r.status === "needs_review");
  const conflictRules    = rules.filter(r => r.status === "conflict");
  const archivedRules    = rules.filter(r => r.status === "archived");

  return (
    <div className="space-y-8">
      <PageHeader
        title="Rules"
        description={`${activeRules.length} active · ${pendingProposals.length} pending review`}
      />

      {/* Pending proposals */}
      {pendingProposals.length > 0 && (
        <section className="space-y-3">
          <SectionLabel label="Pending Proposals" count={pendingProposals.length} color="text-amber" />
          <div className="space-y-2">
            {pendingProposals.map(p => (
              <div key={p.id} className="rounded-md border border-amber/20 bg-amber/5 p-4">
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text leading-relaxed">{p.content}</p>
                    <div className="flex items-center gap-3 mt-2 flex-wrap">
                      <span className="text-[11px] font-mono text-amber/80 bg-amber/10 px-1.5 py-0.5 rounded">{p.rule_type}</span>
                      <span className="text-[11px] text-text-muted font-mono">{confidencePct(p.confidence)} conf</span>
                      {p.tool_scope.length > 0 && (
                        <span className="text-[11px] text-text-faint font-mono">{p.tool_scope.join(", ")}</span>
                      )}
                      <span className="text-[11px] text-text-faint">{relativeTime(p.created_at)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <form action={confirmAction.bind(null, p.id)}>
                      <button type="submit" className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-green-lore/10 text-green-lore border border-green-lore/20 rounded hover:bg-green-lore/20 transition-colors">
                        <CheckCircle className="w-3.5 h-3.5" /> Confirm
                      </button>
                    </form>
                    <form action={rejectAction.bind(null, p.id)}>
                      <button type="submit" className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-red-lore/10 text-red-lore border border-red-lore/20 rounded hover:bg-red-lore/20 transition-colors">
                        <XCircle className="w-3.5 h-3.5" /> Reject
                      </button>
                    </form>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Conflict rules */}
      {conflictRules.length > 0 && (
        <RuleSection
          label="Conflicts"
          rules={conflictRules}
          color="text-red-lore"
          archiveAction={archiveAction}
          activateAction={activateAction}
        />
      )}

      {/* Needs review */}
      {reviewRules.length > 0 && (
        <RuleSection
          label="Needs Review"
          rules={reviewRules}
          color="text-amber"
          archiveAction={archiveAction}
          activateAction={activateAction}
        />
      )}

      {/* Active rules */}
      <RuleSection
        label="Active"
        rules={activeRules}
        color="text-green-lore"
        archiveAction={archiveAction}
        activateAction={activateAction}
      />

      {/* Archived */}
      {archivedRules.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer list-none">
            <SectionLabel label="Archived" count={archivedRules.length} color="text-text-muted" />
          </summary>
          <div className="mt-3">
            <RuleSection
              label=""
              rules={archivedRules}
              color="text-text-muted"
              archiveAction={archiveAction}
              activateAction={activateAction}
            />
          </div>
        </details>
      )}

      {rules.length === 0 && pendingProposals.length === 0 && (
        <div className="text-center py-20">
          <BookOpen className="w-8 h-8 text-text-faint mx-auto mb-3" strokeWidth={1} />
          <p className="text-sm text-text-muted">No rules yet</p>
          <p className="text-xs text-text-faint mt-1">Rules are mined from events. Capture some corrections to get started.</p>
        </div>
      )}
    </div>
  );
}

function SectionLabel({ label, count, color }: { label: string; count?: number; color: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className={`text-xs font-mono font-medium uppercase tracking-widest ${color}`}>{label}</span>
      {count !== undefined && (
        <span className="text-[10px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded">{count}</span>
      )}
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

function RuleSection({
  label, rules, color, archiveAction, activateAction,
}: {
  label: string;
  rules: Awaited<ReturnType<typeof getRules>>["rules"];
  color: string;
  archiveAction: (id: string) => Promise<void>;
  activateAction: (id: string) => Promise<void>;
}) {
  if (rules.length === 0 && label) return null;
  return (
    <section className="space-y-3">
      {label && <SectionLabel label={label} count={rules.length} color={color} />}
      <div className="rounded-md border border-border bg-surface-1 divide-y divide-border">
        {rules.map(rule => (
          <div key={rule.id} className="px-4 py-3 flex items-start gap-4 group">
            <div className="flex-1 min-w-0 space-y-1.5">
              <p className="text-sm text-text leading-relaxed">{rule.content}</p>
              <div className="flex items-center gap-3 flex-wrap">
                <StatusBadge status={rule.status} />
                <span className="text-[11px] font-mono text-text-faint bg-surface-2 px-1.5 py-0.5 rounded">{rule.rule_type}</span>
                <span className="text-[11px] text-text-faint font-mono">{confidencePct(rule.confidence)}</span>
                {rule.tool_scope.length > 0 && (
                  <span className="text-[11px] text-text-faint font-mono">{rule.tool_scope.join(", ")}</span>
                )}
                <span className="text-[11px] text-text-faint">{relativeTime(rule.updated_at)}</span>
              </div>
            </div>
            <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              {rule.status === "archived" ? (
                <form action={activateAction.bind(null, rule.id)}>
                  <button type="submit" className="flex items-center gap-1 px-2.5 py-1 text-[11px] bg-green-lore/10 text-green-lore border border-green-lore/20 rounded hover:bg-green-lore/20 transition-colors">
                    <ShieldCheck className="w-3 h-3" /> Activate
                  </button>
                </form>
              ) : (
                <form action={archiveAction.bind(null, rule.id)}>
                  <button type="submit" className="flex items-center gap-1 px-2.5 py-1 text-[11px] bg-surface-2 text-text-muted border border-border rounded hover:bg-surface-3 transition-colors">
                    <Trash2 className="w-3 h-3" /> Archive
                  </button>
                </form>
              )}
            </div>
          </div>
        ))}
        {rules.length === 0 && (
          <div className="px-4 py-8 text-center text-xs text-text-faint">No rules in this state</div>
        )}
      </div>
    </section>
  );
}
