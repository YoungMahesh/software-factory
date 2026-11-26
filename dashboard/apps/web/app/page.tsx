"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { CachedGitHubRepo } from "@dashboard/types";
import { ChevronDown, ChevronRight, Loader2, RefreshCw, X } from "lucide-react";
import { FactoryAppGrid } from "@/components/builder/factory-app-grid";
import { LaunchProgressCard } from "@/components/builder/launch-progress-card";
import { useDashboard } from "@/components/dashboard-provider";
import { formatDate } from "@/lib/format";

export default function BuilderPage() {
  const {
    apps,
    primes,
    models,
    profiles,
    selectedProfile,
    searchQuery,
    repoCatalog,
    repoRefreshing,
    builderDraft,
    setBuilderDraft,
    builderSubmitting,
    activeLaunch,
    trackLaunch,
    dismissActiveLaunch,
    refreshGithubRepos,
    submitAppPrompt,
    openFactoryApp,
    relaunchFactoryApp,
    deleteFactoryApp,
    openSnapshotModal,
    openLaunchFromSnapshotModal,
  } = useDashboard();

  const [repoSearchQuery, setRepoSearchQuery] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const selectedModelIndex = useMemo(() => {
    const idx = models.findIndex(
      (m) => m.provider === builderDraft.provider && m.model === builderDraft.model,
    );
    return idx >= 0 ? idx : 0;
  }, [models, builderDraft.provider, builderDraft.model]);

  const selectedModel = models[selectedModelIndex] ?? models[0];

  const matchingPrimeSandbox = useMemo(() => {
    const effProfile =
      builderDraft.profile || (selectedProfile !== "all" ? selectedProfile : null);
    const vm = Boolean(builderDraft.vm);
    const mobile =
      !builderDraft.repo &&
      builderDraft.template === "nextjs" &&
      Boolean(builderDraft.mobile_app);
    return (
      primes.find(
        (p) =>
          (p.profile || null) === (effProfile || null) &&
          Boolean(p.vm) === vm &&
          Boolean(p.mobile_app) === mobile &&
          (p.runtime_status === "running" || p.runtime_status === "provisioning"),
      ) ?? null
    );
  }, [primes, builderDraft, selectedProfile]);

  const filteredGithubRepos = useMemo(() => {
    const repos = repoCatalog.repos ?? [];
    const q = repoSearchQuery.toLowerCase().trim();
    if (!q) return repos;
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        (r.description?.toLowerCase().includes(q) ?? false),
    );
  }, [repoCatalog.repos, repoSearchQuery]);

  const customRepoCandidate = useMemo(() => {
    const raw = repoSearchQuery.trim();
    if (!raw || /\s/.test(raw)) return null;
    const lower = raw.toLowerCase();
    const exact = (repoCatalog.repos ?? []).some(
      (r) =>
        r.full_name.toLowerCase() === lower || r.name.toLowerCase() === lower,
    );
    return exact ? null : raw;
  }, [repoCatalog.repos, repoSearchQuery]);

  const filteredApps = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return apps;
    return apps.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.slug.toLowerCase().includes(q) ||
        (a.repo?.toLowerCase().includes(q) ?? false) ||
        (a.branch?.toLowerCase().includes(q) ?? false) ||
        a.prompt.toLowerCase().includes(q) ||
        a.model.toLowerCase().includes(q),
    );
  }, [apps, searchQuery]);

  function toggleSelectRepo(repoItem: CachedGitHubRepo) {
    if (builderDraft.repo === repoItem.full_name) {
      setBuilderDraft((prev) => ({
        ...prev,
        repo: null,
        branch: "",
        web_app: prev.template === "nextjs",
      }));
      return;
    }
    setBuilderDraft((prev) => ({
      ...prev,
      repo: repoItem.full_name,
      branch: repoItem.default_branch || "main",
      mobile_app: false,
      web_app: false,
    }));
  }

  function selectCustomRepo(rawRepo: string) {
    const clean = rawRepo.trim();
    if (!clean) return;
    setBuilderDraft((prev) => ({
      ...prev,
      repo: clean,
      branch: prev.branch || "main",
      mobile_app: false,
      web_app: false,
    }));
    setRepoSearchQuery("");
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      <section className="bg-surface-soft border border-hairline rounded-2xl p-4 sm:p-6 lg:p-8 shadow-sm space-y-4 sm:space-y-5">
        <div className="space-y-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
            <h2 className="text-xl sm:text-3xl font-bold tracking-tight text-ink">
              What do you want to build?
            </h2>

            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2 sm:py-1.5 rounded-xl bg-canvas border border-hairline text-xs max-w-full">
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  matchingPrimeSandbox?.runtime_status === "running"
                    ? "bg-success animate-pulse"
                    : matchingPrimeSandbox?.runtime_status === "provisioning"
                      ? "bg-primary animate-pulse"
                      : "bg-muted-soft"
                }`}
              />
              {matchingPrimeSandbox?.runtime_status === "running" ? (
                <span className="text-body break-words">
                  Prime Sandbox{" "}
                  <span className="font-mono text-ink font-medium break-all">
                    {matchingPrimeSandbox.sandbox_id}
                  </span>{" "}
                  <span className="text-muted">
                    ({matchingPrimeSandbox.app_count} app
                    {matchingPrimeSandbox.app_count === 1 ? "" : "s"})
                  </span>
                </span>
              ) : matchingPrimeSandbox?.runtime_status === "provisioning" ? (
                <span className="text-primary-active">
                  Prime Sandbox booting — new prompts will attach automatically
                </span>
              ) : (
                <span className="text-muted">
                  No active Prime Sandbox — first launch boots one
                </span>
              )}
              <Link
                href="/sandboxes"
                className="text-primary hover:text-primary-active underline-offset-2 hover:underline font-medium"
              >
                Sandboxes
              </Link>
            </div>
          </div>

          <p className="text-xs sm:text-sm text-muted">
            Describe a new app or select a GitHub repository to open in the shared Prime
            Sandbox. Repository lists stay cached until you click Refresh.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-5 items-stretch">
          <div className="lg:col-span-7 flex flex-col justify-between space-y-3 min-w-0">
            <div className="space-y-3">
              {builderDraft.repo && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-3 py-2.5 sm:py-2 rounded-xl bg-primary/10 border border-primary/30 text-xs">
                  <div className="flex flex-wrap items-center gap-2 min-w-0">
                    <span className="px-2 py-0.5 rounded bg-primary/20 text-primary-active font-semibold flex-shrink-0">
                      Repo
                    </span>
                    <span className="font-mono text-ink font-semibold truncate max-w-full">
                      {builderDraft.repo}
                    </span>
                    <span className="text-muted">@</span>
                    <input
                      id="builder-repo-branch"
                      type="text"
                      value={builderDraft.branch}
                      onChange={(e) =>
                        setBuilderDraft((prev) => ({ ...prev, branch: e.target.value }))
                      }
                      placeholder="main"
                      aria-label="Target branch"
                      className="flex-1 min-w-[6rem] sm:flex-initial sm:w-28 bg-canvas border border-hairline rounded-md px-2 py-1 sm:py-0.5 font-mono text-base sm:text-xs text-ink focus:outline-none focus:border-primary"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setBuilderDraft((prev) => ({
                        ...prev,
                        repo: null,
                        branch: "",
                        web_app: prev.template === "nextjs",
                      }))
                    }
                    className="self-start sm:self-auto text-body hover:text-ink px-2.5 py-1 sm:py-0.5 rounded bg-canvas border border-hairline flex-shrink-0 inline-flex items-center gap-1"
                  >
                    <X className="w-3 h-3" />
                    <span>New from scratch</span>
                  </button>
                </div>
              )}

              <textarea
                id="builder-prompt-input"
                rows={5}
                value={builderDraft.prompt}
                onChange={(e) =>
                  setBuilderDraft((prev) => ({ ...prev, prompt: e.target.value }))
                }
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                    e.preventDefault();
                    void submitAppPrompt();
                  }
                }}
                placeholder={
                  builderDraft.repo
                    ? `Optional prompt for ${builderDraft.repo} (leave empty to open directly in T3)...`
                    : "Build a personal habit tracker with daily streaks, analytics chart, and dark mode..."
                }
                className="w-full bg-canvas border border-hairline focus:border-primary rounded-xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-base text-ink placeholder:text-muted-soft focus:outline-none resize-y"
              />
            </div>

            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center justify-between gap-3 pt-1">
                <div className="flex flex-wrap items-center gap-2 text-xs w-full sm:w-auto">
                  <select
                    value={selectedModelIndex}
                    onChange={(e) => {
                      const next = models[Number.parseInt(e.target.value, 10)];
                      if (!next) return;
                      setBuilderDraft((prev) => ({
                        ...prev,
                        provider: next.provider,
                        model: next.model,
                        thought_level:
                          next.thought_levels && next.thought_levels.length > 0
                            ? prev.thought_level
                            : "",
                      }));
                    }}
                    className="w-full sm:w-auto max-w-full bg-canvas border border-hairline rounded-lg px-2.5 py-2 sm:py-1.5 text-base sm:text-xs text-ink focus:outline-none focus:border-primary"
                  >
                    {models.map((m, idx) => (
                      <option key={`${m.provider}:${m.model}`} value={idx}>
                        {m.label}
                      </option>
                    ))}
                  </select>

                  {selectedModel?.thought_levels &&
                    selectedModel.thought_levels.length > 0 && (
                      <select
                        value={builderDraft.thought_level}
                        onChange={(e) =>
                          setBuilderDraft((prev) => ({
                            ...prev,
                            thought_level: e.target.value,
                          }))
                        }
                        className="w-full sm:w-auto max-w-full bg-canvas border border-hairline rounded-lg px-2.5 py-2 sm:py-1.5 text-base sm:text-xs text-ink focus:outline-none focus:border-primary"
                      >
                        <option value="">Thinking: Default</option>
                        {selectedModel.thought_levels.map((opt) => (
                          <option key={opt.id} value={opt.id}>
                            Thinking: {opt.label}
                          </option>
                        ))}
                      </select>
                    )}

                  {!builderDraft.repo && (
                    <div className="inline-flex bg-canvas p-0.5 rounded-lg border border-hairline">
                      <button
                        type="button"
                        onClick={() =>
                          setBuilderDraft((prev) => ({
                            ...prev,
                            template: "nextjs",
                            web_app: true,
                          }))
                        }
                        className={`px-2.5 py-1.5 sm:py-1 rounded-md transition-colors ${
                          builderDraft.template === "nextjs"
                            ? "bg-primary text-on-primary"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        Next.js App
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setBuilderDraft((prev) => ({
                            ...prev,
                            template: "blank",
                            mobile_app: false,
                            web_app: false,
                          }))
                        }
                        className={`px-2.5 py-1.5 sm:py-1 rounded-md transition-colors ${
                          builderDraft.template === "blank"
                            ? "bg-primary text-on-primary"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        Blank Git Repo
                      </button>
                    </div>
                  )}

                  {!builderDraft.repo && builderDraft.template === "nextjs" && (
                    <label className="inline-flex items-center gap-1.5 px-2.5 py-2 sm:py-1.5 rounded-lg bg-canvas border border-hairline text-body cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={builderDraft.mobile_app}
                        onChange={(e) =>
                          setBuilderDraft((prev) => ({
                            ...prev,
                            mobile_app: e.target.checked,
                          }))
                        }
                        className="rounded border-hairline text-primary focus:ring-0"
                      />
                      <span>+ Mobile</span>
                    </label>
                  )}

                  <label
                    title="When checked, appends run-app startup and preview port instructions to the prompt"
                    className="inline-flex items-center gap-1.5 px-2.5 py-2 sm:py-1.5 rounded-lg bg-canvas border border-hairline text-body cursor-pointer select-none"
                  >
                    <input
                      id="builder-webapp-checkbox"
                      type="checkbox"
                      checked={builderDraft.web_app}
                      onChange={(e) =>
                        setBuilderDraft((prev) => ({
                          ...prev,
                          web_app: e.target.checked,
                        }))
                      }
                      className="rounded border-hairline text-primary focus:ring-0"
                    />
                    <span>web app</span>
                  </label>

                  <button
                    type="button"
                    onClick={() => setShowAdvanced((v) => !v)}
                    className="inline-flex items-center gap-1 px-2.5 py-2 sm:py-1.5 rounded-lg bg-canvas hover:bg-surface-card border border-hairline text-muted hover:text-ink transition-colors"
                  >
                    {showAdvanced ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                    <span>Advanced</span>
                  </button>
                </div>

                <button
                  id="builder-submit-btn"
                  type="button"
                  disabled={
                    builderSubmitting ||
                    (!builderDraft.repo && !builderDraft.prompt.trim())
                  }
                  onClick={() => void submitAppPrompt()}
                  className="w-full sm:w-auto inline-flex items-center justify-center px-5 py-3 sm:py-2.5 rounded-xl bg-primary hover:bg-primary-active text-sm font-semibold text-on-primary shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {builderSubmitting && (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  )}
                  <span>
                    {builderSubmitting
                      ? "Starting..."
                      : builderDraft.repo
                        ? "Open Repo"
                        : "Build App"}
                  </span>
                </button>
              </div>

              {showAdvanced && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-hairline text-xs">
                  <div>
                    <label className="block text-muted mb-1">
                      App / Workspace Name (optional)
                    </label>
                    <input
                      type="text"
                      value={builderDraft.name}
                      onChange={(e) =>
                        setBuilderDraft((prev) => ({ ...prev, name: e.target.value }))
                      }
                      placeholder="Auto-derived from repo or prompt"
                      className="w-full bg-canvas border border-hairline rounded-lg px-3 py-2 sm:py-1.5 text-base sm:text-xs text-ink focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-muted mb-1">Modal Profile</label>
                    <select
                      value={builderDraft.profile}
                      onChange={(e) =>
                        setBuilderDraft((prev) => ({ ...prev, profile: e.target.value }))
                      }
                      className="w-full bg-canvas border border-hairline rounded-lg px-3 py-2 sm:py-1.5 text-base sm:text-xs text-ink focus:outline-none focus:border-primary"
                    >
                      <option value="">Active Default Profile</option>
                      {profiles.map((p) => (
                        <option key={p.name} value={p.name}>
                          {p.name}
                          {p.active ? " (active)" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex items-center gap-2 text-body cursor-pointer select-none py-1">
                      <input
                        type="checkbox"
                        checked={builderDraft.vm}
                        onChange={(e) =>
                          setBuilderDraft((prev) => ({ ...prev, vm: e.target.checked }))
                        }
                        className="rounded border-hairline text-primary focus:ring-0"
                      />
                      <span>VM Sandbox (Docker runtime)</span>
                    </label>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div
            id="github-repos-panel"
            className="lg:col-span-5 bg-canvas border border-hairline rounded-xl p-3.5 sm:p-4 flex flex-col justify-between space-y-3 min-w-0"
          >
            <div className="space-y-2.5 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-body truncate">
                    GitHub Repositories
                  </h3>
                  {repoCatalog.org && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-surface-card text-primary-active font-mono truncate max-w-[7rem]">
                      {repoCatalog.org}
                    </span>
                  )}
                </div>
                <button
                  id="refresh-github-repos-btn"
                  type="button"
                  disabled={repoRefreshing}
                  onClick={() => void refreshGithubRepos()}
                  className="inline-flex items-center px-2.5 py-1.5 sm:py-1 rounded-lg bg-surface-soft hover:bg-surface-card border border-hairline text-xs font-medium text-ink transition-colors disabled:opacity-50 flex-shrink-0"
                >
                  <RefreshCw
                    className={`w-3.5 h-3.5 mr-1 ${repoRefreshing ? "animate-spin" : ""}`}
                  />
                  <span>{repoRefreshing ? "Refreshing..." : "Refresh"}</span>
                </button>
              </div>

              <input
                id="github-repo-search"
                type="text"
                value={repoSearchQuery}
                onChange={(e) => setRepoSearchQuery(e.target.value)}
                placeholder="Filter repos or enter owner/repo..."
                className="w-full bg-surface-soft border border-hairline focus:border-primary rounded-lg px-3 py-2 sm:py-1.5 text-base sm:text-xs text-ink placeholder:text-muted-soft focus:outline-none"
              />

              {customRepoCandidate && (
                <button
                  type="button"
                  onClick={() => selectCustomRepo(customRepoCandidate)}
                  className="w-full text-left px-2.5 py-2 sm:py-1.5 rounded-lg bg-primary/10 hover:bg-primary/20 border border-primary/30 text-xs text-primary-active flex items-center justify-between gap-2"
                >
                  <span className="truncate">
                    Use repository{" "}
                    <span className="font-mono font-semibold">{customRepoCandidate}</span>
                  </span>
                  <span className="text-[10px] flex-shrink-0 font-semibold">Select</span>
                </button>
              )}

              <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                {filteredGithubRepos.map((repoItem) => {
                  const selected = builderDraft.repo === repoItem.full_name;
                  return (
                    <button
                      key={repoItem.full_name}
                      type="button"
                      onClick={() => toggleSelectRepo(repoItem)}
                      className={`w-full text-left px-3 py-2.5 sm:py-2 rounded-lg border transition-colors space-y-0.5 ${
                        selected
                          ? "bg-primary/15 border-primary text-ink"
                          : "bg-surface-soft hover:bg-surface-card border-hairline text-body"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs font-medium truncate min-w-0">
                          {repoItem.name}
                        </span>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                              repoItem.private
                                ? "bg-accent-amber/20 text-ink"
                                : "bg-surface-card text-muted"
                            }`}
                          >
                            {repoItem.private ? "private" : "public"}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-card text-muted font-mono max-w-[5.5rem] truncate">
                            {repoItem.default_branch}
                          </span>
                        </div>
                      </div>
                      {repoItem.description && (
                        <div className="text-[11px] text-muted line-clamp-1">
                          {repoItem.description}
                        </div>
                      )}
                    </button>
                  );
                })}

                {(repoCatalog.repos ?? []).length === 0 && (
                  <div className="py-6 px-3 text-center text-xs text-muted border border-dashed border-hairline rounded-lg">
                    No cached repositories yet. Click{" "}
                    <span className="text-ink font-medium">Refresh</span> to load from
                    GitHub.
                  </div>
                )}

                {(repoCatalog.repos ?? []).length > 0 &&
                  filteredGithubRepos.length === 0 && (
                    <div className="py-6 px-3 text-center text-xs text-muted">
                      No cached repositories match your filter.
                    </div>
                  )}
              </div>
            </div>

            <div className="pt-2 border-t border-hairline flex flex-wrap items-center justify-between gap-1 text-[11px] text-muted">
              <span>
                {repoCatalog.refreshed_at
                  ? `Updated ${formatDate(repoCatalog.refreshed_at)}`
                  : "Not fetched yet (manual refresh only)"}
              </span>
              <span>
                {(repoCatalog.repos ?? []).length} repo
                {(repoCatalog.repos ?? []).length === 1 ? "" : "s"}
              </span>
            </div>
          </div>
        </div>
      </section>

      {activeLaunch && (
        <LaunchProgressCard
          launch={activeLaunch}
          onDismiss={dismissActiveLaunch}
          onRetry={(appId) => void relaunchFactoryApp({ app_id: appId }, { resume: true })}
        />
      )}

      <FactoryAppGrid
        apps={filteredApps}
        onOpen={(app) => void openFactoryApp(app)}
        onSnapshot={(target) => openSnapshotModal(target)}
        onTrackProgress={(requestId) => void trackLaunch(requestId)}
        onRelaunch={(app, resume) => void relaunchFactoryApp(app, { resume })}
        onResumeSnapshot={(target) => openLaunchFromSnapshotModal(target)}
        onDelete={(app) => void deleteFactoryApp(app)}
      />
    </div>
  );
}
