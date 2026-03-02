import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-surface flex flex-col items-center justify-center px-6">
      {/* Logo */}
      <div className="flex items-center gap-2 mb-10">
        <div className="w-9 h-9 rounded-sm bg-amber flex items-center justify-center">
          <span className="text-surface font-mono font-bold text-base">L</span>
        </div>
        <span className="font-mono text-2xl font-semibold tracking-tight text-text">lore</span>
      </div>

      {/* Headline */}
      <div className="text-center max-w-xl space-y-4 mb-10">
        <h1 className="text-3xl sm:text-4xl font-semibold text-text tracking-tight">
          Organizational memory for AI-native teams
        </h1>
        <p className="text-text-muted text-base leading-relaxed">
          Lore captures every AI correction and distills them into rules your whole team benefits from.
        </p>
      </div>

      {/* CTAs */}
      <div className="flex items-center gap-4">
        <Link
          href="/sign-up"
          className="px-5 py-2.5 rounded bg-amber text-surface font-medium text-sm hover:bg-amber/90 transition-colors"
        >
          Get started
        </Link>
        <Link
          href="/sign-in"
          className="px-5 py-2.5 rounded border border-border text-text-muted text-sm hover:text-text hover:border-text/30 transition-colors"
        >
          Sign in
        </Link>
      </div>
    </main>
  );
}
