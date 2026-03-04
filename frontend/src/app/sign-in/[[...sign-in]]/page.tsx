import { SignIn } from "@clerk/nextjs";
import { Cpu, ShieldCheck, Network, Lightbulb } from "lucide-react";
import Link from "next/link";

const FEATURES = [
  { Icon: Lightbulb, text: "Captures every AI correction your team makes" },
  { Icon: ShieldCheck, text: "Mines corrections into org-wide rules automatically" },
  { Icon: Network, text: "Injects rules into every AI call, automatically" },
];

export default function SignInPage() {
  return (
    <div className="min-h-screen flex">
      {/* Left panel */}
      <div className="hidden lg:flex relative flex-col justify-between w-1/2 bg-surface-1 border-r border-border p-12 overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-30" />
        <div className="orb orb-amber w-[500px] h-[500px] -bottom-32 -left-20 opacity-40" />

        <div className="relative">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-sm bg-amber flex items-center justify-center">
              <Cpu className="w-4 h-4 text-surface" strokeWidth={2.5} />
            </div>
            <span className="font-mono text-lg font-semibold tracking-tight text-text">lore</span>
          </Link>
        </div>

        <div className="relative space-y-8">
          <div>
            <h2 className="text-2xl font-semibold text-text tracking-tight leading-snug">
              Your team's AI<br />
              <span className="text-gradient-amber">remembers its mistakes.</span>
            </h2>
            <p className="mt-3 text-sm text-text-muted leading-relaxed max-w-xs">
              Lore turns every human correction into persistent organizational memory. 
              Rules that apply to everyone, automatically.
            </p>
          </div>

          <div className="space-y-4">
            {FEATURES.map(({ Icon, text }) => (
              <div key={text} className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-sm bg-amber/10 border border-amber/20 flex items-center justify-center shrink-0 mt-0.5">
                  <Icon className="w-3.5 h-3.5 text-amber" strokeWidth={1.75} />
                </div>
                <p className="text-sm text-text-muted">{text}</p>
              </div>
            ))}
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
            <h1 className="text-xl font-semibold text-text">Welcome back</h1>
            <p className="text-sm text-text-muted mt-1">Sign in to your workspace</p>
          </div>
          <SignIn fallbackRedirectUrl="/dashboard" />
        </div>
      </div>
    </div>
  );
}
