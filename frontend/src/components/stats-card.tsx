import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatsCardProps {
  label: string;
  value: string | number;
  sub?: string;
  Icon?: LucideIcon;
  accent?: "amber" | "green" | "red" | "blue" | "default";
}

const accentMap = {
  amber:   "text-amber border-amber/20 bg-amber/5",
  green:   "text-green-lore border-green-lore/20 bg-green-lore/5",
  red:     "text-red-lore border-red-lore/20 bg-red-lore/5",
  blue:    "text-blue-lore border-blue-lore/20 bg-blue-lore/5",
  default: "text-text border-border bg-surface-1",
};

export default function StatsCard({ label, value, sub, Icon, accent = "default" }: StatsCardProps) {
  const color = accentMap[accent];
  return (
    <div className={cn("rounded-md border p-4 space-y-2", color)}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-muted uppercase tracking-widest font-mono">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-50" strokeWidth={1.5} />}
      </div>
      <p className="text-3xl font-mono font-semibold tracking-tight">{value}</p>
      {sub && <p className="text-[11px] text-text-muted">{sub}</p>}
    </div>
  );
}
