"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  GitBranch,
  Globe,
  Loader2,
  RefreshCw,
  Rocket,
  Terminal,
  X,
  XCircle,
} from "lucide-react";
import {
  extractApiError,
  isActiveDashboardDeploy,
  type DashboardDeployRecord,
  type DeployerStatusPayload,
} from "@/lib/deploy-types";

function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return "—";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString();
}

function StatusBadge({ status }: { status: DashboardDeployRecord["status"] }) {
  switch (status) {
    case "ready":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/15 text-success border border-success/30">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Ready
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-error/15 text-error border border-error/30">
          <XCircle className="w-3.5 h-3.5" />
          Failed
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-primary/15 text-primary-active border border-primary/30">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      );
  }
}

export function DeployerConsole() {
  const [status, setStatus] = useState<DeployerStatusPayload | null>(null);
  const [activeDeploy, setActiveDeploy] = useState<DashboardDeployRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const logBoxRef = useRef<HTMLDivElement | null>(null);

  const loadStatus = useCallback(async (withSpinner = false) => {
    if (withSpinner) setLoading(true);
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      if (!res.ok) {
        throw new Error(await extractApiError(res));
      }
      const data = (await res.json()) as DeployerStatusPayload;
      setStatus(data);
      setActiveDeploy(data.latest_deploy);
      setBannerError(data.control_plane_error);
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/status", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error(await extractApiError(res));
        return (await res.json()) as DeployerStatusPayload;
      })
      .then((data) => {
        if (cancelled) return;
        setStatus(data);
        setActiveDeploy(data.latest_deploy);
        setBannerError(data.control_plane_error);
      })
      .catch((err) => {
        if (!cancelled) {
          setBannerError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runningDeployId = isActiveDashboardDeploy(activeDeploy)
    ? (activeDeploy?.deploy_id ?? null)
    : null;

  useEffect(() => {
    if (!runningDeployId) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/deploy/${encodeURIComponent(runningDeployId)}`, {
          cache: "no-store",
        });
        if (!res.ok || cancelled) return;
        const next = (await res.json()) as DashboardDeployRecord;
        if (cancelled) return;
        setActiveDeploy(next);
        if (!isActiveDashboardDeploy(next)) {
          void loadStatus(false);
        }
      } catch {
        // Polling is best-effort; retry on next tick.
      }
    }, 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [runningDeployId, loadStatus]);

  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [activeDeploy?.logs.length]);

  const triggerDeploy = useCallback(async () => {
    setConfirmOpen(false);
    setSubmitting(true);
    setBannerError(null);
    try {
      const res = await fetch("/api/deploy", { method: "POST" });
      if (!res.ok) {
        throw new Error(await extractApiError(res));
      }
      const record = (await res.json()) as DashboardDeployRecord;
      setActiveDeploy(record);
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, []);

  const deployRunning = submitting || isActiveDashboardDeploy(activeDeploy);
  const targetDomain = status?.apps_base_domain ?? "App Base Domain";
  const targetUrl = status?.target_url ?? activeDeploy?.target_url ?? null;
  const cpVersion = status?.control_plane_version;

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink">
      <header className="border-b border-hairline bg-surface-soft/90 backdrop-blur sticky top-0 z-30">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center text-on-primary shadow-sm flex-shrink-0">
              <Rocket className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h1 className="text-base sm:text-lg font-semibold tracking-tight text-ink flex flex-wrap items-center gap-2">
                <span>Dashboard Deployer</span>
                {cpVersion?.commit_short && cpVersion.commit_short !== "unknown" && (
                  <span
                    title={`Control Plane Ref: ${cpVersion.ref} | Commit: ${cpVersion.commit}`}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-surface-card text-muted font-mono border border-hairline"
                  >
                    CP {cpVersion.commit_short}
                    {cpVersion.dirty ? "*" : ""}
                  </span>
                )}
                {status?.deployer_commit && status.deployer_commit !== "unknown" && (
                  <span
                    title={`Deployer Commit: ${status.deployer_commit}`}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-surface-card text-muted font-mono border border-hairline"
                  >
                    Deployer {status.deployer_commit.slice(0, 7)}
                  </span>
                )}
              </h1>
            </div>
          </div>

          <button
            type="button"
            disabled={loading}
            onClick={() => void loadStatus(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-canvas hover:bg-surface-card border border-hairline text-xs sm:text-sm font-medium text-ink transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-primary" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6">
        {bannerError && (
          <div className="rounded-xl border border-error/40 bg-error/10 p-4 text-sm text-error flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div className="min-w-0 break-words">{bannerError}</div>
          </div>
        )}

        <section className="rounded-2xl border border-hairline bg-surface-soft p-5 sm:p-6 shadow-2xs space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1.5 min-w-0">
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
                <Globe className="w-3.5 h-3.5" />
                <span>Target Production Stack</span>
              </div>
              <h2 className="text-xl font-semibold text-ink">Sandbox Web Dashboard</h2>
              <p className="text-sm text-body">
                Clones the latest <span className="font-mono text-ink">main</span> branch from
                GitHub inside the Hosted Sandbox Control Plane and rebuilds{" "}
                <span className="font-mono text-ink">dashboard/</span> on{" "}
                <span className="font-mono text-ink">{targetDomain}</span>.
              </p>
            </div>

            <button
              type="button"
              disabled={deployRunning || loading || status?.control_plane_configured === false}
              onClick={() => setConfirmOpen(true)}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-primary hover:bg-primary-active text-on-primary text-sm font-semibold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              {deployRunning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{activeDeploy?.current_label || "Deploying..."}</span>
                </>
              ) : (
                <>
                  <Rocket className="w-4 h-4" />
                  <span>Deploy Sandbox Web Dashboard</span>
                </>
              )}
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-hairline">
            <div className="rounded-xl bg-canvas border border-hairline p-3.5 space-y-1">
              <div className="text-xs text-muted">App Base Domain</div>
              {targetUrl ? (
                <a
                  href={targetUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-mono font-medium text-primary-active hover:underline break-all"
                >
                  <span>{targetDomain}</span>
                  <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
                </a>
              ) : (
                <div className="text-sm font-mono text-muted">Not configured</div>
              )}
            </div>

            <div className="rounded-xl bg-canvas border border-hairline p-3.5 space-y-1">
              <div className="text-xs text-muted">Source Branch</div>
              <div className="inline-flex items-center gap-1.5 text-sm font-mono font-medium text-ink">
                <GitBranch className="w-3.5 h-3.5 text-muted" />
                <span>main</span>
              </div>
            </div>

            <div className="rounded-xl bg-canvas border border-hairline p-3.5 space-y-1">
              <div className="text-xs text-muted">Live Dashboard Commit</div>
              <div className="text-sm font-mono font-medium text-ink">
                {loading
                  ? "Checking..."
                  : status?.live_dashboard_commit
                    ? status.live_dashboard_commit
                    : status?.live_dashboard_reachable
                      ? "Live (commit unknown)"
                      : "Unreachable"}
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-hairline bg-canvas p-5 sm:p-6 shadow-2xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-0.5">
              <h3 className="text-base font-semibold text-ink">Latest Deployment</h3>
              <p className="text-xs text-muted">
                {activeDeploy
                  ? `Job ${activeDeploy.deploy_id} · Updated ${formatTimestamp(activeDeploy.updated_at)}`
                  : "No deployments recorded yet."}
              </p>
            </div>
            {activeDeploy && <StatusBadge status={activeDeploy.status} />}
          </div>

          {activeDeploy && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                <div className="rounded-lg bg-surface-soft border border-hairline p-3">
                  <div className="text-xs text-muted mb-0.5">Current Step</div>
                  <div className="font-medium text-ink break-words">{activeDeploy.current_label}</div>
                </div>
                <div className="rounded-lg bg-surface-soft border border-hairline p-3">
                  <div className="text-xs text-muted mb-0.5">Deployed Commit</div>
                  <div className="font-mono text-ink">{activeDeploy.commit_short ?? "—"}</div>
                </div>
                <div className="rounded-lg bg-surface-soft border border-hairline p-3">
                  <div className="text-xs text-muted mb-0.5">Started</div>
                  <div className="text-ink">{formatTimestamp(activeDeploy.created_at)}</div>
                </div>
              </div>

              {activeDeploy.error && (
                <div className="rounded-xl border border-error/40 bg-error/10 p-3.5 text-sm text-error break-words">
                  {activeDeploy.error}
                </div>
              )}

              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-muted">
                  <span className="inline-flex items-center gap-1.5 font-medium">
                    <Terminal className="w-3.5 h-3.5" />
                    Deployment Logs
                  </span>
                  {activeDeploy.status === "ready" && (activeDeploy.target_url || targetUrl) && (
                    <a
                      href={activeDeploy.target_url || targetUrl || "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary-active font-medium hover:underline"
                    >
                      <span>Open Sandbox Web Dashboard</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
                <div
                  ref={logBoxRef}
                  className="rounded-xl bg-surface-dark text-on-dark font-mono text-xs p-4 h-64 overflow-y-auto space-y-1 border border-surface-dark-elevated"
                >
                  {activeDeploy.logs.length > 0 ? (
                    activeDeploy.logs.map((line, idx) => (
                      <div key={idx} className="whitespace-pre-wrap break-words leading-relaxed">
                        {line}
                      </div>
                    ))
                  ) : (
                    <div className="text-on-dark-soft italic">Waiting for deployment output...</div>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </main>

      {confirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="deploy-confirm-title"
          className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-3 sm:p-4"
          onClick={() => setConfirmOpen(false)}
        >
          <div
            className="bg-canvas border border-hairline rounded-2xl max-w-md w-full p-5 sm:p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 id="deploy-confirm-title" className="text-base font-semibold text-ink">
                Deploy Sandbox Web Dashboard
              </h3>
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                aria-label="Close confirmation"
                className="p-1 text-muted hover:text-ink rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-sm text-body">
              Pull the latest <span className="font-mono text-ink">main</span> branch from GitHub
              and rebuild and deploy <span className="font-mono text-ink">dashboard/</span> (and
              Caddy apex routing) to{" "}
              <span className="font-mono text-ink">{targetDomain}</span>? Modal Control Plane
              functions will not be redeployed.
            </p>

            <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 pt-2 border-t border-hairline">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="px-4 py-2 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-sm font-medium text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void triggerDeploy()}
                className="px-4 py-2 rounded-lg bg-primary hover:bg-primary-active text-sm font-semibold text-on-primary"
              >
                Deploy Now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
