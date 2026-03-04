import { SignUp } from "@clerk/nextjs";
import { Cpu, ShieldCheck, Network, Lightbulb } from "lucide-react";
import Link from "next/link";

const STEPS = [
  { label: "01", text: "Create your workspace" },
  { label: "02", text: "Install the SDK in 2 minutes" },
  { label: "03", text: "Corrections start flowing automatically" },
];

export default function SignUpPage() {
  return (
    <div className="min-h-screen flex">
      {/* Left panel */}
      <div className="hidden lg:flex relative flex-col justify-between w-1/2 bg-surface-1 border-r border-border p-12 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30" />
        <div className="orb orb-green w-[400px] h-[400px] top-0 right-0 opacity-30" />
        <div className="orb orb-amber w-[400px] h-[400px] bottom-0 -left-20 opacity-30" />

        <div className="relative">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-sm bg-amber flex items-center justify-center">
              <Cpu className="w-4 h-4 text-surface" strokeWidth={2.5} />
            </div>
            <span className="font-mono text-lg font-semibold tracking-tight text-text">lore</span>
          </Link>
        </div>

        <div className="relative space-y-10">
          <div>
            <h2 className="text-2xl font-semibold text-text tracking-tight leading-snug">
              Start capturing<br />
              <span className="text-gradient-amber">institutional memory.</span>
            </h2>
            <p className="mt-3 text-sm text-text-muted leading-relaxed max-w-xs">
              Set up in minutes. Every correction your team makes becomes available 
              to every AI tool you use.
            </p>
          </div>

          <div className="space-y-5">
            {STEPS.map(({ label, text }) => (
              <div key={label} className="flex items-center gap-4">
                <span className="font-mono text-xs text-amber/60 w-4 shrink-0">{label}</span>
                <div className="h-px flex-1 bg-border" />
                <p className="text-sm text-text-muted w-48 text-right">{text}</p>
              </div>
            ))}
          </div>

          <div className="inline-flex items-center gap-2 bg-amber/10 border border-amber/20 text-amber text-xs font-mono px-3 py-1.5 rounded-full">
            <div className="w-1.5 h-1.5 rounded-full bg-amber animate-pulse" />
            Free beta — no credit card required
          </div>
        </div>

        <div className="relative">
          <p className="text-xs text-text-faint">© 2026 Lore — Organizational AI memory</p>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex flex-col items-center justify-center bg-surface px-6 py-12">
        {/* Mobile logo */}
        <div className="lg:hidden flex items-center gap-2 mb-8">
          <div className="w-7 h-7 rounded-sm bg-amber flex items-center justify-center">
            <Cpu className="w-4 h-4 text-surface" strokeWidth={2.5} />
          </div>
          <span className="font-mono text-lg font-semibold tracking-tight text-text">lore</span>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-6">
            <h1 className="text-xl font-semibold text-text">Create your workspace</h1>
            <p className="text-sm text-text-muted mt-1">Free forever — upgrade when you need more</p>
          </div>
          <SignUp fallbackRedirectUrl="/dashboard" />
        </div>
      </div>
    </div>
  );
}
