"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  BookOpen,
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
  isActiveDocsDeploy,
  type AnyDeployRecord,
  type AnyDeployStatus,
  type DashboardDeployRecord,
  type DeployerStatusPayload,
  type DocsDeployRecord,
} from "@/lib/deploy-types";

type ConfirmTarget = "dashboard" | "docs" | null;

function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return "—";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString();
}

function StatusBadge({ status }: { status: AnyDeployStatus }) {
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

interface DeployStackSectionProps {
  eyebrowIcon: ReactNode;
  eyebrow: string;
  title: string;
  description: ReactNode;
  buttonLabel: string;
  buttonDisabled: boolean;
  deployRunning: boolean;
  activeDeploy: AnyDeployRecord | null;
  onDeployClick: () => void;
  domainTileLabel: string;
  domainText: string | null;
  targetUrl: string | null;
  liveCommitLabel: string;
  liveCommit: string | null;
  liveReachable: boolean;
  loading: boolean;
  latestTitle: string;
  emptyText: string;
  openLabel: string;
}

function DeployStackSection({
  eyebrowIcon,
  eyebrow,
  title,
  description,
  buttonLabel,
  buttonDisabled,
  deployRunning,
  activeDeploy,
  onDeployClick,
  domainTileLabel,
  domainText,
  targetUrl,
  liveCommitLabel,
  liveCommit,
  liveReachable,
  loading,
  latestTitle,
  emptyText,
  openLabel,
}: DeployStackSectionProps) {
  const logBoxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [activeDeploy?.logs.length]);

  const resolvedOpenUrl = activeDeploy?.target_url || targetUrl;

  return (
    <section className="rounded-2xl border border-hairline bg-surface-soft p-5 sm:p-6 shadow-2xs space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
            {eyebrowIcon}
            <span>{eyebrow}</span>
          </div>
          <h2 className="text-xl font-semibold text-ink">{title}</h2>
          <p className="text-sm text-body">{description}</p>
        </div>

        <button
          type="button"
          disabled={buttonDisabled}
          onClick={onDeployClick}
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
              <span>{buttonLabel}</span>
            </>
          )}
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-hairline">
        <div className="rounded-xl bg-canvas border border-hairline p-3.5 space-y-1">
          <div className="text-xs text-muted">{domainTileLabel}</div>
          {targetUrl && domainText ? (
            <a
              href={targetUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-mono font-medium text-primary-active hover:underline break-all"
            >
              <span>{domainText}</span>
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
          <div className="text-xs text-muted">{liveCommitLabel}</div>
          <div className="text-sm font-mono font-medium text-ink">
            {loading
              ? "Checking..."
              : liveCommit
                ? liveCommit
                : liveReachable
                  ? "Live (commit unknown)"
                  : "Unreachable"}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-hairline bg-canvas p-4 sm:p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-0.5">
            <h3 className="text-base font-semibold text-ink">{latestTitle}</h3>
            <p className="text-xs text-muted">
              {activeDeploy
                ? `Job ${activeDeploy.deploy_id} · Updated ${formatTimestamp(activeDeploy.updated_at)}`
                : emptyText}
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
                {activeDeploy.status === "ready" && resolvedOpenUrl && (
                  <a
                    href={resolvedOpenUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-primary-active font-medium hover:underline"
                  >
                    <span>{openLabel}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
              <div
                ref={logBoxRef}
                className="rounded-xl bg-surface-dark text-on-dark font-mono text-xs p-4 h-56 overflow-y-auto space-y-1 border border-surface-dark-elevated"
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
      </div>
    </section>
  );
}

export function DeployerConsole() {
  const [status, setStatus] = useState<DeployerStatusPayload | null>(null);
  const [activeDeploy, setActiveDeploy] = useState<DashboardDeployRecord | null>(null);
  const [activeDocsDeploy, setActiveDocsDeploy] = useState<DocsDeployRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [submittingDashboard, setSubmittingDashboard] = useState(false);
  const [submittingDocs, setSubmittingDocs] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget>(null);
  const [bannerError, setBannerError] = useState<string | null>(null);

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
      setActiveDocsDeploy(data.latest_docs_deploy);
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
        setActiveDocsDeploy(data.latest_docs_deploy);
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

  const runningDocsDeployId = isActiveDocsDeploy(activeDocsDeploy)
    ? (activeDocsDeploy?.deploy_id ?? null)
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
    if (!runningDocsDeployId) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/docs/deploy/${encodeURIComponent(runningDocsDeployId)}`, {
          cache: "no-store",
        });
        if (!res.ok || cancelled) return;
        const next = (await res.json()) as DocsDeployRecord;
        if (cancelled) return;
        setActiveDocsDeploy(next);
        if (!isActiveDocsDeploy(next)) {
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
  }, [runningDocsDeployId, loadStatus]);

  const triggerDashboardDeploy = useCallback(async () => {
    setConfirmTarget(null);
    setSubmittingDashboard(true);
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
      setSubmittingDashboard(false);
    }
  }, []);

  const triggerDocsDeploy = useCallback(async () => {
    setConfirmTarget(null);
    setSubmittingDocs(true);
    setBannerError(null);
    try {
      const res = await fetch("/api/docs/deploy", { method: "POST" });
      if (!res.ok) {
        throw new Error(await extractApiError(res));
      }
      const record = (await res.json()) as DocsDeployRecord;
      setActiveDocsDeploy(record);
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmittingDocs(false);
    }
  }, []);

  const dashboardDeployRunning = submittingDashboard || isActiveDashboardDeploy(activeDeploy);
  const docsDeployRunning = submittingDocs || isActiveDocsDeploy(activeDocsDeploy);
  const targetDomain = status?.apps_base_domain ?? "App Base Domain";
  const docsDomain = status?.apps_base_domain
    ? `docs.${status.apps_base_domain}`
    : "docs.<APPS_BASE_DOMAIN>";
  const targetUrl = status?.target_url ?? activeDeploy?.target_url ?? null;
  const docsTargetUrl = status?.docs_target_url ?? activeDocsDeploy?.target_url ?? null;
  const cpVersion = status?.control_plane_version;
  const cpDisabled = loading || status?.control_plane_configured === false;

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

        <DeployStackSection
          eyebrowIcon={<Globe className="w-3.5 h-3.5" />}
          eyebrow="Target Production Stack"
          title="Sandbox Web Dashboard"
          description={
            <>
              Clones the latest <span className="font-mono text-ink">main</span> branch from GitHub
              inside the Hosted Sandbox Control Plane and rebuilds{" "}
              <span className="font-mono text-ink">dashboard/</span> on{" "}
              <span className="font-mono text-ink">{targetDomain}</span>.
            </>
          }
          buttonLabel="Deploy Sandbox Web Dashboard"
          buttonDisabled={dashboardDeployRunning || cpDisabled}
          deployRunning={dashboardDeployRunning}
          activeDeploy={activeDeploy}
          onDeployClick={() => setConfirmTarget("dashboard")}
          domainTileLabel="App Base Domain"
          domainText={status?.apps_base_domain ? targetDomain : null}
          targetUrl={targetUrl}
          liveCommitLabel="Live Dashboard Commit"
          liveCommit={status?.live_dashboard_commit ?? null}
          liveReachable={status?.live_dashboard_reachable ?? false}
          loading={loading}
          latestTitle="Latest Dashboard Deployment"
          emptyText="No dashboard deployments recorded yet."
          openLabel="Open Sandbox Web Dashboard"
        />

        <DeployStackSection
          eyebrowIcon={<BookOpen className="w-3.5 h-3.5" />}
          eyebrow="Target Cloudflare Pages Stack"
          title="Documentation Web App"
          description={
            <>
              Clones the latest <span className="font-mono text-ink">main</span> branch from GitHub
              inside the Hosted Sandbox Control Plane, builds{" "}
              <span className="font-mono text-ink">docs/</span> with Zensical, and publishes to
              Cloudflare Pages at <span className="font-mono text-ink">{docsDomain}</span>.
            </>
          }
          buttonLabel="Deploy Documentation Web App"
          buttonDisabled={docsDeployRunning || cpDisabled}
          deployRunning={docsDeployRunning}
          activeDeploy={activeDocsDeploy}
          onDeployClick={() => setConfirmTarget("docs")}
          domainTileLabel="Documentation Domain"
          domainText={status?.apps_base_domain ? docsDomain : null}
          targetUrl={docsTargetUrl}
          liveCommitLabel="Live Docs Commit"
          liveCommit={status?.live_docs_commit ?? null}
          liveReachable={status?.live_docs_reachable ?? false}
          loading={loading}
          latestTitle="Latest Documentation Deployment"
          emptyText="No documentation deployments recorded yet."
          openLabel="Open Documentation Web App"
        />
      </main>

      {confirmTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="deploy-confirm-title"
          className="fixed inset-0 z-50 overflow-y-auto bg-ink/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-3 sm:p-4"
          onClick={() => setConfirmTarget(null)}
        >
          <div
            className="bg-canvas border border-hairline rounded-2xl max-w-md w-full p-5 sm:p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 id="deploy-confirm-title" className="text-base font-semibold text-ink">
                {confirmTarget === "dashboard"
                  ? "Deploy Sandbox Web Dashboard"
                  : "Deploy Documentation Web App"}
              </h3>
              <button
                type="button"
                onClick={() => setConfirmTarget(null)}
                aria-label="Close confirmation"
                className="p-1 text-muted hover:text-ink rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {confirmTarget === "dashboard" ? (
              <p className="text-sm text-body">
                Pull the latest <span className="font-mono text-ink">main</span> branch from GitHub
                and rebuild and deploy <span className="font-mono text-ink">dashboard/</span> (and
                Caddy apex routing) to{" "}
                <span className="font-mono text-ink">{targetDomain}</span>? Hosted Sandbox Control
                Plane functions will not be redeployed.
              </p>
            ) : (
              <p className="text-sm text-body">
                Pull the latest <span className="font-mono text-ink">main</span> branch from GitHub,
                build <span className="font-mono text-ink">docs/</span> with Zensical, and publish to
                Cloudflare Pages at <span className="font-mono text-ink">{docsDomain}</span>? VPS
                containers and Hosted Sandbox Control Plane functions will not be modified.
              </p>
            )}

            <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 pt-2 border-t border-hairline">
              <button
                type="button"
                onClick={() => setConfirmTarget(null)}
                className="px-4 py-2 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-sm font-medium text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() =>
                  void (confirmTarget === "dashboard"
                    ? triggerDashboardDeploy()
                    : triggerDocsDeploy())
                }
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
