"use client";

import type { FactoryAppView, SandboxCost } from "@dashboard/types";
import { formatDate, formatUsdCost } from "@/lib/format";
import type { SnapshotTarget } from "@/components/modals/snapshot-create-modal";
import type { SnapshotLaunchTarget } from "@/components/modals/snapshot-launch-modal";

export function FactoryAppGrid({
  apps,
  sandboxCosts,
  onOpen,
  onSnapshot,
  onTrackProgress,
  onRelaunch,
  onResumeSnapshot,
}: {
  apps: FactoryAppView[];
  sandboxCosts?: Record<string, SandboxCost>;
  onOpen: (app: FactoryAppView) => void;
  onSnapshot: (target: SnapshotTarget) => void;
  onTrackProgress: (requestId: string) => void;
  onRelaunch: (app: FactoryAppView, resume: boolean) => void;
  onResumeSnapshot: (target: SnapshotLaunchTarget) => void;
}) {
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Factory Apps
        </h3>
        <span className="text-xs text-muted">{apps.length} app(s)</span>
      </div>

      {apps.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {apps.map((app) => {
            const badgeClass =
              app.runtime_status === "running"
                ? "bg-success/15 text-ink border-success/40"
                : app.runtime_status === "provisioning"
                  ? "bg-primary/15 text-primary-active border-primary/30"
                  : app.runtime_status === "failed"
                    ? "bg-error/15 text-error border-error/30"
                    : "bg-surface-card text-muted border-hairline";

            const workspaceBadge = app.repo
              ? app.repo
              : app.template === "nextjs"
                ? app.mobile_app
                  ? "Next.js + Expo"
                  : "Next.js"
                : "Blank Git";

            return (
              <div
                key={app.app_id}
                className="bg-surface-soft border border-hairline rounded-2xl p-4 sm:p-5 flex flex-col justify-between space-y-4 hover:border-muted-soft transition-colors min-w-0"
              >
                <div className="space-y-2.5 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h4 className="text-base font-semibold text-ink truncate">
                        {app.title}
                      </h4>
                      <div className="text-xs font-mono text-muted truncate">
                        {app.workspace_path || `/root/${app.slug}`}
                      </div>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-medium border flex-shrink-0 ${badgeClass}`}
                    >
                      {app.runtime_status.toUpperCase()}
                    </span>
                  </div>

                  {app.prompt ? (
                    <p className="text-xs text-body line-clamp-2 break-words">{app.prompt}</p>
                  ) : (
                    <p className="text-xs text-muted italic">
                      Opened repository without initial prompt
                    </p>
                  )}

                  <div className="flex flex-wrap gap-1.5 text-[11px] font-mono">
                    <span className="px-2 py-0.5 rounded bg-surface-card text-body-strong border border-hairline max-w-full truncate">
                      {workspaceBadge}
                    </span>
                    {(app.worktree_branch || (app.repo && app.branch)) && (
                      <span className="px-2 py-0.5 rounded bg-success/15 text-ink max-w-full truncate">
                        @ {app.worktree_branch || app.branch}
                      </span>
                    )}
                    <span className="px-2 py-0.5 rounded bg-primary/10 text-primary-active max-w-full truncate">
                      {app.model}
                    </span>
                    {app.dev_port ? (
                      <span className="px-2 py-0.5 rounded bg-accent-teal/15 text-ink">
                        :{app.dev_port}
                      </span>
                    ) : (
                      app.web_app && (
                        <span className="px-2 py-0.5 rounded bg-accent-teal/15 text-ink">
                          web app
                        </span>
                      )
                    )}
                    {app.sandbox_id && (() => {
                      const sbCost = sandboxCosts?.[app.sandbox_id]?.cost_usd;
                      const costNote =
                        typeof sbCost === "number"
                          ? ` · est. host cost ${formatUsdCost(sbCost)} (shared)`
                          : "";
                      return (
                        <span
                          title={`Sandbox ${app.sandbox_id}${costNote}`}
                          className="px-2 py-0.5 rounded bg-canvas border border-hairline text-muted max-w-full truncate"
                        >
                          {app.sandbox_id}
                        </span>
                      );
                    })()}
                    {app.database_name && (
                      <span className="px-2 py-0.5 rounded bg-success/15 text-ink max-w-full truncate">
                        DB: {app.database_name}
                      </span>
                    )}
                  </div>

                  {app.runtime_status === "failed" && app.last_error && (
                    <div className="text-[11px] text-error line-clamp-2 break-words">
                      {app.last_error}
                    </div>
                  )}
                </div>

                <div className="pt-3 border-t border-hairline flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
                  <span className="text-muted">{formatDate(app.created_at)}</span>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {app.runtime_status === "running" && (
                      <button
                        type="button"
                        onClick={() => onOpen(app)}
                        className="px-3 py-2 sm:py-1.5 rounded-lg bg-primary hover:bg-primary-active text-on-primary font-medium"
                      >
                        Open in T3
                      </button>
                    )}
                    {app.runtime_status === "running" && app.sandbox_id && (
                      <button
                        type="button"
                        onClick={() =>
                          onSnapshot({
                            id: app.sandbox_id!,
                            name: app.sandbox_name || app.slug,
                            profile: app.profile,
                          })
                        }
                        title="Capture a filesystem snapshot of the shared Prime Sandbox (includes all hosted apps)"
                        className="px-2.5 py-2 sm:py-1.5 rounded-lg bg-canvas hover:bg-surface-card text-body border border-hairline"
                      >
                        Snapshot Sandbox
                      </button>
                    )}
                    {app.runtime_status === "provisioning" && app.latest_request_id && (
                      <button
                        type="button"
                        onClick={() => onTrackProgress(app.latest_request_id!)}
                        className="px-3 py-2 sm:py-1.5 rounded-lg bg-primary/15 hover:bg-primary/25 text-primary-active border border-primary/30 font-medium"
                      >
                        Progress
                      </button>
                    )}
                    {app.runtime_status === "failed" &&
                      app.failed_step &&
                      app.sandbox_id && (
                        <button
                          type="button"
                          onClick={() => onRelaunch(app, true)}
                          className="px-3 py-2 sm:py-1.5 rounded-lg bg-error hover:bg-error/90 text-on-primary font-medium"
                        >
                          Retry Step
                        </button>
                      )}
                    {(app.runtime_status === "stopped" ||
                      app.runtime_status === "failed") && (
                      <button
                        type="button"
                        onClick={() => onRelaunch(app, false)}
                        className="px-3 py-2 sm:py-1.5 rounded-lg bg-primary hover:bg-primary-active text-on-primary font-medium"
                      >
                        Relaunch
                      </button>
                    )}
                    {(app.runtime_status === "stopped" ||
                      app.runtime_status === "failed") &&
                      app.snapshot_image_id && (
                        <button
                          type="button"
                          onClick={() =>
                            onResumeSnapshot({
                              image_id: app.snapshot_image_id!,
                              name: app.snapshot_name || app.slug,
                              profile: app.profile,
                              is_vm: app.vm,
                            })
                          }
                          className="px-2.5 py-2 sm:py-1.5 rounded-lg bg-canvas hover:bg-surface-card text-primary-active border border-hairline"
                        >
                          Resume Snapshot
                        </button>
                      )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-surface-soft border border-dashed border-hairline rounded-2xl p-8 sm:p-10 text-center text-sm text-muted">
          No Factory Apps yet. Enter a prompt above to start your first app.
        </div>
      )}
    </section>
  );
}
