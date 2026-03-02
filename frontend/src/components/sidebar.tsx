"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  ShieldCheck,
  MessageSquareWarning,
  Network,
  KeyRound,
  Cpu,
  ChevronRight,
} from "lucide-react";

const NAV = [
  { href: "/dashboard",             label: "Overview",    Icon: LayoutDashboard, exact: true },
  { href: "/dashboard/rules",       label: "Rules",       Icon: ShieldCheck },
  { href: "/dashboard/corrections", label: "Corrections", Icon: MessageSquareWarning },
  { href: "/dashboard/entities",    label: "Entities",    Icon: Network },
  { href: "/dashboard/api-keys",    label: "API Keys",    Icon: KeyRound },
];

export default function Sidebar() {
  const path = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 w-56 flex flex-col bg-surface-1 border-r border-border z-30">
      {/* Logo */}
      <div className="h-14 flex items-center gap-2.5 px-4 border-b border-border">
        <div className="w-6 h-6 rounded-sm bg-amber flex items-center justify-center shrink-0">
          <Cpu className="w-3.5 h-3.5 text-surface" strokeWidth={2.5} />
        </div>
        <span className="font-mono text-base font-semibold tracking-tight text-text">lore</span>
        <span className="ml-auto font-mono text-[10px] text-text-faint bg-surface-2 px-1.5 py-0.5 rounded">
          v0.1
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-2 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, label, Icon, exact }) => {
          const active = exact ? path === href : path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-all duration-150",
                active
                  ? "bg-amber/10 text-amber border border-amber/20"
                  : "text-text-muted hover:text-text hover:bg-surface-2 border border-transparent"
              )}
            >
              <Icon
                className={cn("w-4 h-4 shrink-0", active ? "text-amber" : "text-text-faint group-hover:text-text-muted")}
                strokeWidth={1.75}
              />
              <span className="flex-1">{label}</span>
              {active && <ChevronRight className="w-3 h-3 text-amber/60" />}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="h-14 flex items-center gap-3 px-4 border-t border-border">
        <UserButton
          appearance={{
            elements: {
              avatarBox: "w-7 h-7",
              userButtonTrigger: "focus:shadow-none",
            },
          }}
        />
        <div className="flex-1 min-w-0">
          <p className="text-xs text-text truncate">Account</p>
          <p className="text-[10px] text-text-faint">workspace admin</p>
        </div>
      </div>
    </aside>
  );
}
