import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatDistanceToNow, format } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function relativeTime(date: string | null | undefined): string {
  if (!date) return "never";
  try {
    return formatDistanceToNow(new Date(date), { addSuffix: true });
  } catch {
    return "unknown";
  }
}

export function shortDate(date: string | null | undefined): string {
  if (!date) return "—";
  try {
    return format(new Date(date), "MMM d, yyyy");
  } catch {
    return "—";
  }
}

export function truncate(str: string, n: number): string {
  return str.length > n ? str.slice(0, n) + "…" : str;
}

export function confidencePct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: "Active",
    proposed: "Proposed",
    conflict: "Conflict",
    needs_review: "Needs Review",
    archived: "Archived",
    pending: "Pending",
    confirmed: "Confirmed",
    rejected: "Rejected",
  };
  return map[status] ?? status;
}
