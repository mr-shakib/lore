import { cn } from "@/lib/utils";

interface BadgeProps {
  status: string;
  className?: string;
}

const statusMap: Record<string, string> = {
  active:       "badge-active",
  proposed:     "badge-proposed",
  conflict:     "badge-conflict",
  needs_review: "badge-needs_review",
  archived:     "badge-archived",
  pending:      "badge-proposed",
  confirmed:    "badge-active",
  rejected:     "badge-archived",
};

const labelMap: Record<string, string> = {
  active:       "Active",
  proposed:     "Proposed",
  conflict:     "Conflict",
  needs_review: "Needs Review",
  archived:     "Archived",
  pending:      "Pending",
  confirmed:    "Confirmed",
  rejected:     "Rejected",
};

export default function StatusBadge({ status, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-mono font-medium",
        statusMap[status] ?? "badge-archived",
        className
      )}
    >
      {labelMap[status] ?? status}
    </span>
  );
}
