import Link from "next/link";
import {
  Cpu, ArrowRight, ShieldCheck, Network, Lightbulb,
  MessageSquareWarning, Code2, Zap, BookOpen, ChevronRight
} from "lucide-react";

// ── Nav ───────────────────────────────────────────────────────────────────────

function Nav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-border/60">
      <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-sm bg-amber flex items-center justify-center">
            <Cpu className="w-3.5 h-3.5 text-surface" strokeWidth={2.5} />
          </div>
          <span className="font-mono text-base font-semibold tracking-tight text-text">lore</span>
          <span className="font-mono text-[10px] text-text-faint bg-surface-2 border border-border px-1.5 py-0.5 rounded">beta</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/sign-in"
            className="text-sm text-text-muted hover:text-text transition-colors px-3 py-1.5"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="flex items-center gap-1.5 text-sm bg-amber text-surface font-medium px-3.5 py-1.5 rounded hover:bg-amber-bright transition-colors"
          >
            Get started <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </nav>
  );
}

// ── Hero ──────────────────────────────────────────────────────────────────────

const SDK_SNIPPET = `from loremem import LoreClient

lore = LoreClient(api_key="sk-lore-...")

# Capture a correction when a user fixes AI output
lore.capture(
    event_type="correction",
    actor_id="eng-team",
    summary="Don't recommend PG for write-heavy queues",
    source_tool="cursor",
)

# Retrieve the current rules for your context
rules = lore.context.get(tool="cursor")
# → "Use Redis for write-heavy workloads (3 corrections)"`;

function Hero() {
  return (
    <section className="relative pt-32 pb-24 overflow-hidden">
      {/* Background grid */}
      <div className="absolute inset-0 bg-grid opacity-40" />

      {/* Ambient orbs */}
      <div className="orb orb-amber w-[600px] h-[600px] -top-48 -left-24 opacity-50" />
      <div className="orb orb-green w-[400px] h-[400px] top-32 right-0 opacity-40" />

      <div className="relative max-w-5xl mx-auto px-6">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-amber/10 border border-amber/20 text-amber text-xs font-mono px-3 py-1.5 rounded-full mb-8 animate-fade-up">
          <div className="w-1.5 h-1.5 rounded-full bg-amber animate-pulse-dot" />
          Now in beta — capturing AI corrections in production
        </div>

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold text-text tracking-tight max-w-3xl leading-[1.1] animate-fade-up delay-100">
          Every AI correction.{" "}
          <span className="text-gradient-amber">Learned once.</span>{" "}
          Applied everywhere.
        </h1>

        <p className="mt-6 text-base sm:text-lg text-text-muted max-w-xl leading-relaxed animate-fade-up delay-200">
          Lore captures every time a human corrects an AI output, mines those
          patterns into organizational rules, and injects them into every AI
          interaction — automatically.
        </p>

        {/* CTAs */}
        <div className="flex items-center gap-4 mt-8 animate-fade-up delay-300">
          <Link
            href="/sign-up"
            className="flex items-center gap-2 bg-amber text-surface font-medium text-sm px-5 py-2.5 rounded hover:bg-amber-bright transition-all hover:shadow-lg hover:shadow-amber/20"
          >
            Start for free <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/sign-in"
            className="flex items-center gap-2 text-sm text-text-muted border border-border px-5 py-2.5 rounded hover:border-border/80 hover:text-text hover:bg-surface-1 transition-colors"
          >
            Sign in to dashboard
          </Link>
        </div>

        {/* SDK code block */}
        <div className="mt-16 relative animate-fade-up delay-400">
          <div className="code-block">
            {/* Window chrome */}
            <div className="flex items-center gap-1.5 px-4 py-3 border-b border-border/60">
              <div className="w-2.5 h-2.5 rounded-full bg-red-lore/40" />
              <div className="w-2.5 h-2.5 rounded-full bg-amber/40" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-lore/40" />
              <span className="ml-3 text-[11px] font-mono text-text-faint">quickstart.py</span>
              <div className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-text-faint">
                <Code2 className="w-3 h-3" />
                pip install loremem
              </div>
            </div>
            <pre className="p-5 text-[13px] font-mono leading-relaxed overflow-x-auto">
              <CodeHighlight code={SDK_SNIPPET} />
            </pre>
          </div>

          {/* Floating badge */}
          <div className="absolute -right-4 -top-4 bg-green-lore/10 border border-green-lore/20 text-green-lore text-[11px] font-mono px-2.5 py-1 rounded-full flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-green-lore animate-pulse" />
            SDK available
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Simple syntax-like colouring (no external deps) ──────────────────────────

function CodeHighlight({ code }: { code: string }) {
  const lines = code.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <div key={i} className="flex">
          <span className="select-none w-6 shrink-0 text-right mr-4 text-text-faint/40 text-[11px]">{i + 1}</span>
          <span>
            {line.startsWith("#") ? (
              <span className="text-text-faint/60">{line}</span>
            ) : line.includes("from ") || line.includes("import ") ? (
              <>
                <span className="text-blue-lore/80">
                  {line.match(/^(from|import)/)?.[0]}
                </span>
                <span className="text-text-muted">{line.slice(line.match(/^(from|import)/)?.[0].length ?? 0)}</span>
              </>
            ) : line.includes("=") && !line.startsWith(" ") ? (
              <>
                <span className="text-text">{line.split("=")[0]}</span>
                <span className="text-text-faint">=</span>
                <span className="text-amber/90">{line.split("=").slice(1).join("=")}</span>
              </>
            ) : line.includes('→') ? (
              <span className="text-green-lore/80">{line}</span>
            ) : (
              <span className="text-text-muted">{line}</span>
            )}
          </span>
        </div>
      ))}
    </>
  );
}

// ── How it works ──────────────────────────────────────────────────────────────

const STEPS = [
  {
    step: "01",
    icon: MessageSquareWarning,
    title: "Capture corrections",
    body: "Instrument your AI tools with the Lore SDK. Every time a human corrects an AI output, a structured event is captured with context, tool, and actor.",
    accent: "amber",
  },
  {
    step: "02",
    icon: Lightbulb,
    title: "Mine patterns",
    body: "Lore's pattern engine clusters similar corrections across sessions and actors, then proposes behavioral rules with confidence scores for your review.",
    accent: "blue",
  },
  {
    step: "03",
    icon: ShieldCheck,
    title: "Apply everywhere",
    body: "Confirmed rules are injected as context into every AI call in your workspace. New hires and new models benefit from institutional knowledge instantly.",
    accent: "green",
  },
];

function HowItWorks() {
  return (
    <section className="py-24 relative">
      <div className="absolute inset-0 bg-grid opacity-20" />
      <div className="relative max-w-5xl mx-auto px-6">
        <div className="text-center mb-14">
          <h2 className="text-2xl sm:text-3xl font-semibold text-text tracking-tight">
            From correction to institutional knowledge
          </h2>
          <p className="mt-3 text-text-muted text-sm max-w-lg mx-auto">
            Three steps from a single human fix to organisation-wide AI alignment.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {STEPS.map(({ step, icon: Icon, title, body, accent }, idx) => (
            <div
              key={step}
              className="relative rounded-lg border border-border bg-surface-1 p-6 hover:border-border/80 transition-colors group"
            >
              {/* Step line connector */}
              {idx < STEPS.length - 1 && (
                <div className="hidden md:block absolute top-10 -right-3 w-6 h-px bg-border z-10" />
              )}

              <div className="flex items-center gap-3 mb-4">
                <div className={`w-8 h-8 rounded-sm flex items-center justify-center shrink-0 ${
                  accent === "amber" ? "bg-amber/10 border border-amber/20" :
                  accent === "blue"  ? "bg-blue-lore/10 border border-blue-lore/20" :
                                       "bg-green-lore/10 border border-green-lore/20"
                }`}>
                  <Icon className={`w-4 h-4 ${
                    accent === "amber" ? "text-amber" :
                    accent === "blue"  ? "text-blue-lore" :
                                         "text-green-lore"
                  }`} strokeWidth={1.75} />
                </div>
                <span className={`font-mono text-xs ${
                  accent === "amber" ? "text-amber/60" :
                  accent === "blue"  ? "text-blue-lore/60" :
                                       "text-green-lore/60"
                }`}>{step}</span>
              </div>

              <h3 className="text-sm font-semibold text-text tracking-tight mb-2">{title}</h3>
              <p className="text-xs text-text-muted leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Features ──────────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Network,
    title: "Entity Memory",
    body: "Lore builds a graph of every entity your team references — people, codebases, customers, tools. Rules are scoped to entities automatically.",
    accent: "blue",
  },
  {
    icon: Zap,
    title: "Real-time Context API",
    body: "Pull the active rule set for any tool/context combination in a single API call. Works with any LLM orchestration framework.",
    accent: "amber",
  },
  {
    icon: BookOpen,
    title: "Rule Validation",
    body: "Proposed rules sit in review until a human confirms them. Conflicts are detected automatically. Stale rules expire after 90 days of no support.",
    accent: "green",
  },
  {
    icon: Cpu,
    title: "SDK-first",
    body: "Python and TypeScript SDKs with < 5ms overhead. Works alongside any AI framework: LangChain, LlamaIndex, raw OpenAI, or your own agent.",
    accent: "amber",
  },
];

function Features() {
  return (
    <section className="py-24 border-t border-border/40">
      <div className="max-w-5xl mx-auto px-6">
        <div className="mb-14">
          <h2 className="text-2xl sm:text-3xl font-semibold text-text tracking-tight">
            Built for AI-native teams
          </h2>
          <p className="mt-3 text-text-muted text-sm max-w-lg">
            Lore is not a prompt manager. It's persistent, schema-free institutional memory
            that evolves as your team uses AI.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {FEATURES.map(({ icon: Icon, title, body, accent }) => (
            <div
              key={title}
              className="rounded-lg border border-border bg-surface-1 p-5 hover:bg-surface-2 transition-colors group"
            >
              <div className="flex items-start gap-4">
                <div className={`mt-0.5 w-7 h-7 rounded-sm flex items-center justify-center shrink-0 ${
                  accent === "amber" ? "bg-amber/10" :
                  accent === "blue"  ? "bg-blue-lore/10" :
                                       "bg-green-lore/10"
                }`}>
                  <Icon className={`w-3.5 h-3.5 ${
                    accent === "amber" ? "text-amber" :
                    accent === "blue"  ? "text-blue-lore" :
                                         "text-green-lore"
                  }`} strokeWidth={1.75} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text mb-1.5">{title}</h3>
                  <p className="text-xs text-text-muted leading-relaxed">{body}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── CTA ───────────────────────────────────────────────────────────────────────

function CTA() {
  return (
    <section className="py-24 relative overflow-hidden border-t border-border/40">
      <div className="orb orb-amber w-[500px] h-[500px] -bottom-48 left-1/2 -translate-x-1/2 opacity-30" />
      <div className="relative max-w-5xl mx-auto px-6 text-center">
        <h2 className="text-3xl sm:text-4xl font-semibold text-text tracking-tight mb-4">
          Stop letting corrections disappear.
        </h2>
        <p className="text-text-muted text-base max-w-md mx-auto mb-8">
          Every AI mistake your team corrects today is an institutional lesson.<br />
          Lore makes sure it sticks.
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link
            href="/sign-up"
            className="flex items-center gap-2 bg-amber text-surface font-medium text-sm px-6 py-3 rounded hover:bg-amber-bright transition-all hover:shadow-lg hover:shadow-amber/20"
          >
            Get started free <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <p className="mt-4 text-xs text-text-faint">
          No credit card required · Python & TypeScript SDK · Self-serve setup in minutes
        </p>
      </div>
    </section>
  );
}

// ── Footer ────────────────────────────────────────────────────────────────────

function Footer() {
  return (
    <footer className="border-t border-border/40 py-8">
      <div className="max-w-5xl mx-auto px-6 flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-sm bg-amber flex items-center justify-center">
            <Cpu className="w-3 h-3 text-surface" strokeWidth={2.5} />
          </div>
          <span className="font-mono text-sm font-semibold text-text">lore</span>
        </div>
        <div className="flex items-center gap-6 text-xs text-text-faint">
          <Link href="/sign-in" className="hover:text-text-muted transition-colors">Sign in</Link>
          <Link href="/sign-up" className="hover:text-text-muted transition-colors">Sign up</Link>
          <span>© 2026 Lore</span>
        </div>
      </div>
    </footer>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  return (
    <div className="min-h-screen bg-surface noise">
      <Nav />
      <Hero />
      <HowItWorks />
      <Features />
      <CTA />
      <Footer />
    </div>
  );
}
