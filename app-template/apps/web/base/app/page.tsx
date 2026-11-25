import { HealthStatusBadge } from "./health-badge";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 bg-canvas">
      <div className="max-w-2xl w-full space-y-8 text-center">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface-card border border-hairline text-sm text-muted">
            <span className="w-2 h-2 rounded-full bg-success"></span>
            Monorepo Template Ready
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-ink">
            Create Base App
          </h1>
          <p className="text-lg text-body">
            A typesafe, bare-minimum starter powered by Next.js 16, Tailwind CSS v4, and pnpm workspaces.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left">
          <div className="p-5 rounded-xl border border-hairline bg-surface-soft">
            <h3 className="font-semibold text-ink text-base mb-1">Web Workspace</h3>
            <p className="text-sm text-muted mb-3">Next.js 16 App Router with React 19 and Tailwind CSS v4.</p>
            <HealthStatusBadge />
          </div>

          <div className="p-5 rounded-xl border border-hairline bg-surface-soft">
            <h3 className="font-semibold text-ink text-base mb-1">Shared Packages</h3>
            <p className="text-sm text-muted mb-2">Centralized styling and shared contracts.</p>
            <div className="flex flex-wrap gap-2 text-xs font-mono">
              <span className="px-2 py-0.5 rounded bg-surface-card border border-hairline">@repo/theme</span>
              <span className="px-2 py-0.5 rounded bg-surface-card border border-hairline">@repo/types</span>
            </div>
          </div>
        </div>

        <div className="text-sm text-muted">
          Get started by editing <code className="font-mono text-ink bg-surface-card px-1.5 py-0.5 rounded border border-hairline">apps/web/app/page.tsx</code>
        </div>
      </div>
    </main>
  );
}
