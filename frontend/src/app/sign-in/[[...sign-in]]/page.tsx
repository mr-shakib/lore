import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface">
      <div className="w-full max-w-md space-y-8">
        {/* Logo */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2">
            <div className="w-8 h-8 rounded-sm bg-amber flex items-center justify-center">
              <span className="text-surface font-mono font-bold text-sm">L</span>
            </div>
            <span className="font-mono text-xl font-semibold tracking-tight text-text">lore</span>
          </div>
          <p className="text-text-muted text-sm">Organizational memory for AI-native teams</p>
        </div>
        <SignIn fallbackRedirectUrl="/dashboard" />
      </div>
    </div>
  );
}
