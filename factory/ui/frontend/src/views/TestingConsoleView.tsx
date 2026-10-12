import React, { useState, useEffect } from "react";
import {
  Play,
  RotateCw,
  Box,
  Cpu,
  History,
  XCircle,
  Eye,
  Lock,
} from "lucide-react";
import { Repo, Job, ScratchMetadata, Milestone, Issue, LaunchJobParams } from "../types";
import { StageStepper } from "../components/StageStepper";
import { TerminalLogViewer } from "../components/TerminalLogViewer";
import { fetchScratch, fetchMilestones } from "../api";

interface TestingConsoleViewProps {
  repos: Repo[];
  selectedRepo: string;
  onSelectRepo: (repo: string) => void;
  onRefreshRepos: () => void;
  activeJob: Job | null;
  logs?: string[];
  jobs: Job[];
  onLaunch: (params: LaunchJobParams) => void;
  onCancel: (jobId: string) => void;
  onSelectJob: (job: Job) => void;
  onClearLogs?: () => void;
}

export const TestingConsoleView: React.FC<TestingConsoleViewProps> = ({
  repos,
  selectedRepo,
  onSelectRepo,
  onRefreshRepos,
  activeJob,
  logs = [],
  jobs,
  onLaunch,
  onCancel,
  onSelectJob,
  onClearLogs,
}) => {
  const [scratchMeta, setScratchMeta] = useState<ScratchMetadata | null>(null);
  const [milestonesMeta, setMilestonesMeta] = useState<Milestone[]>([]);
  const [feature, setFeature] = useState<string>("");
  const [customFeature, setCustomFeature] = useState<string>("");
  const [issue, setIssue] = useState<string>("");
  const [customIssue, setCustomIssue] = useState<string>("");
  const [model, setModel] = useState<string>("deepseek-v4.1-flash");
  const [vm, setVm] = useState<boolean>(false);
  const [dev, setDev] = useState<boolean>(false);
  const [loadingMeta, setLoadingMeta] = useState<boolean>(false);

  // Discover features / issues when repo changes
  useEffect(() => {
    if (!selectedRepo) {
      setScratchMeta(null);
      setMilestonesMeta([]);
      return;
    }

    let isCancelled = false;
    setLoadingMeta(true);

    Promise.all([
      fetchScratch(selectedRepo).catch(() => null),
      fetchMilestones(selectedRepo).catch(() => ({ repo: selectedRepo, milestones: [] })),
    ])
      .then(([scratchRes, msRes]) => {
        if (isCancelled) return;
        setScratchMeta(scratchRes);
        setMilestonesMeta(msRes?.milestones || []);
      })
      .finally(() => {
        if (!isCancelled) setLoadingMeta(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [selectedRepo]);

  // Derived available features from scratch + milestones
  const availableFeatures: { slug: string; source: "scratch" | "github" }[] = [];
  if (scratchMeta?.features) {
    scratchMeta.features.forEach((f) => {
      availableFeatures.push({ slug: f.slug, source: "scratch" });
    });
  }
  milestonesMeta.forEach((m) => {
    if (!availableFeatures.some((f) => f.slug === m.title)) {
      availableFeatures.push({ slug: m.title, source: "github" });
    }
  });

  // Derived available issues for selected feature
  const effectiveFeature = feature === "__custom__" ? customFeature : feature;
  const availableIssues: Issue[] = [];

  if (feature && feature !== "__custom__") {
    // 1. From scratch
    const scratchFeat = scratchMeta?.features?.find((f) => f.slug === feature);
    if (scratchFeat) {
      scratchFeat.issues.forEach((iss) => {
        availableIssues.push({
          number: iss.id,
          title: iss.title || `Issue ${iss.id}`,
          status: "ready-for-agent",
          blocked_by: [],
        });
      });
    }

    // 2. From GitHub milestones
    const ms = milestonesMeta.find((m) => m.title === feature);
    if (ms) {
      ms.issues.forEach((iss) => {
        if (!availableIssues.some((ai) => String(ai.number) === String(iss.number))) {
          availableIssues.push(iss);
        }
      });
    }
  }

  // Preview selected issue
  const effectiveIssueId = issue === "__custom__" ? customIssue : issue;
  const selectedIssueObj = availableIssues.find(
    (i) => String(i.number) === String(effectiveIssueId)
  );

  const handleLaunchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRepo) return;
    onLaunch({
      repo: selectedRepo,
      feature: effectiveFeature || undefined,
      issue: effectiveIssueId || undefined,
      model,
      vm,
      dev,
    });
  };

  return (
    <div id="console-view" className="flex flex-col space-y-6 max-w-7xl mx-auto px-4 py-6">
      {/* Top Controls Grid: Launch Form & Repository Selection */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Repository & Feature Selection */}
        <div className="lg:col-span-1 bg-slate-900/60 rounded-xl border border-slate-800 p-5 space-y-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <Box className="w-4 h-4 text-indigo-400" />
              <span>Target Repository</span>
              {repos.find((r) => r.name === selectedRepo)?.private && (
                <span
                  data-testid="console-repo-private-badge"
                  className="flex items-center text-[10px] font-medium px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300 border border-slate-700 space-x-1"
                  title="Private repository"
                >
                  <Lock className="w-2.5 h-2.5 text-slate-400" />
                  <span>Private</span>
                </span>
              )}
            </h2>
            <button
              id="btn-refresh-repos"
              type="button"
              onClick={onRefreshRepos}
              className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              title="Refresh repositories"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Organization Repositories
            </label>
            <select
              id="select-repo"
              value={selectedRepo}
              onChange={(e) => onSelectRepo(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Select a repository...</option>
              {repos.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name} {r.is_tanstack_compatible ? "✦ (TanStack)" : ""}{r.private ? " 🔒" : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Feature / Milestone Selector */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Milestone (Feature)
            </label>
            <select
              id="select-feature"
              value={feature}
              disabled={!selectedRepo || loadingMeta}
              onChange={(e) => {
                setFeature(e.target.value);
                setIssue("");
              }}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
            >
              <option value="">(None / Root frontier)</option>
              {availableFeatures.map((f) => (
                <option key={f.slug} value={f.slug}>
                  {f.slug} ({f.source})
                </option>
              ))}
              <option value="__custom__">Custom feature slug...</option>
            </select>

            {feature === "__custom__" && (
              <input
                id="input-feature-custom"
                type="text"
                value={customFeature}
                onChange={(e) => setCustomFeature(e.target.value)}
                placeholder="e.g. inventory-management"
                className="mt-2 w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            )}
          </div>

          {/* Issue / Ticket Selector */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Ticket (Issue)
            </label>
            <select
              id="select-issue"
              value={issue}
              disabled={!selectedRepo || loadingMeta}
              onChange={(e) => setIssue(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
            >
              <option value="">(Autonomous Frontier Batch)</option>
              {availableIssues.map((iss) => (
                <option key={String(iss.number)} value={String(iss.number)}>
                  #{iss.number} — {iss.title}
                </option>
              ))}
              <option value="__custom__">Custom issue ID...</option>
            </select>

            {issue === "__custom__" && (
              <input
                id="input-issue-custom"
                type="text"
                value={customIssue}
                onChange={(e) => setCustomIssue(e.target.value)}
                placeholder="e.g. 01 or 42"
                className="mt-2 w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            )}
          </div>

          {/* Issue Badge Preview */}
          {selectedIssueObj && (
            <div
              id="issue-badge-preview"
              className="p-3 bg-slate-950 rounded-lg border border-slate-800/80 text-xs space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span id="preview-title" className="font-semibold text-slate-200 truncate">
                  #{selectedIssueObj.number}: {selectedIssueObj.title}
                </span>
                <span
                  id="preview-status-badge"
                  className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-indigo-950 text-indigo-300 border border-indigo-800/60"
                >
                  {selectedIssueObj.status}
                </span>
              </div>
              {selectedIssueObj.blocked_by && selectedIssueObj.blocked_by.length > 0 && (
                <div id="preview-details" className="text-[11px] text-amber-400 font-mono">
                  Blocked by: {selectedIssueObj.blocked_by.join(", ")}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Columns: Launch Parameters Form */}
        <div className="lg:col-span-2 bg-slate-900/60 rounded-xl border border-slate-800 p-5 shadow-sm flex flex-col justify-between">
          <form id="launch-form" onSubmit={handleLaunchSubmit} className="space-y-4">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span>Launch Parameters</span>
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  LLM Model
                </label>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                >
                  <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash (Recommended)</option>
                  <option value="mimo-v2.6-flash">MiMo-V2.6-Flash</option>
                </select>
              </div>

              <div className="flex flex-col justify-end space-y-2">
                <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    id="check-vm"
                    type="checkbox"
                    checked={vm}
                    onChange={(e) => setVm(e.target.checked)}
                    className="w-4 h-4 rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-0"
                  />
                  <span>Launch in VM Sandbox (Full VM with Docker)</span>
                </label>

                <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={dev}
                    onChange={(e) => setDev(e.target.checked)}
                    className="w-4 h-4 rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-0"
                  />
                  <span>Dev Preview Mode (Port 3000 keep-alive)</span>
                </label>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between">
              <div className="text-xs text-slate-400">
                Target:{" "}
                <span className="font-mono text-indigo-300 font-medium">
                  {selectedRepo || "No repo selected"}
                </span>
                {effectiveFeature ? ` / ${effectiveFeature}` : ""}
                {effectiveIssueId ? ` (Ticket #${effectiveIssueId})` : ""}
              </div>

              <button
                id="btn-launch"
                type="submit"
                disabled={!selectedRepo}
                className="flex items-center space-x-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:pointer-events-none text-white text-xs font-semibold shadow-md transition-colors"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Launch Assembly Line</span>
              </button>
            </div>
          </form>

          {/* Active Job Header Banner (if any) */}
          {activeJob && (
            <div className="mt-4 p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 uppercase font-mono">Job ID</span>
                  <span id="active-job-id" className="text-xs font-mono font-bold text-slate-200">
                    {activeJob.id}
                  </span>
                </div>

                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 uppercase font-mono">Target</span>
                  <span id="active-job-target" className="text-xs font-mono text-slate-300">
                    {activeJob.repo} / {activeJob.feature}
                  </span>
                </div>

                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 uppercase font-mono">Status</span>
                  <span
                    id="active-job-status"
                    className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-indigo-950 text-indigo-300 font-semibold"
                  >
                    {activeJob.status}
                  </span>
                </div>

                {activeJob.duration && (
                  <div className="flex flex-col">
                    <span className="text-[10px] text-slate-500 uppercase font-mono">Duration</span>
                    <span id="active-job-timer" className="text-xs font-mono text-slate-300">
                      {activeJob.duration.toFixed(1)}s
                    </span>
                  </div>
                )}
              </div>

              {activeJob.status === "RUNNING" && (
                <button
                  id="btn-cancel"
                  type="button"
                  onClick={() => onCancel(activeJob.id)}
                  className="flex items-center space-x-1 px-3 py-1.5 rounded bg-red-950 hover:bg-red-900 border border-red-800 text-red-200 text-xs font-semibold transition-colors"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  <span>Cancel Job</span>
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Stage Stepper */}
      {activeJob && (
        <div className="w-full">
          <StageStepper currentStage={activeJob.stage} />
        </div>
      )}

      {/* Terminal Log Viewer */}
      <div className="h-96 w-full">
        <TerminalLogViewer logs={logs} onClear={onClearLogs} />
      </div>

      {/* Job History Table */}
      <div className="bg-slate-900/60 rounded-xl border border-slate-800 p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
            <History className="w-4 h-4 text-indigo-400" />
            <span>Job History</span>
          </h2>
          <span id="history-count" className="text-xs font-mono text-slate-400">
            {jobs.length} jobs
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 text-[11px] font-mono text-slate-400 bg-slate-950/40">
              <tr>
                <th className="py-2.5 px-3">Job ID</th>
                <th className="py-2.5 px-3">Repo</th>
                <th className="py-2.5 px-3">Feature</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Stage</th>
                <th className="py-2.5 px-3">Created</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="history-table-body" className="divide-y divide-slate-800/60 font-mono">
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 italic">
                    No jobs recorded.
                  </td>
                </tr>
              ) : (
                jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-indigo-300">{j.id}</td>
                    <td className="py-2.5 px-3 text-slate-300">{j.repo}</td>
                    <td className="py-2.5 px-3 text-slate-400">{j.feature || "—"}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          j.status === "SUCCESS"
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                            : j.status === "FAILED"
                            ? "bg-rose-950 text-rose-300 border border-rose-800"
                            : j.status === "RUNNING"
                            ? "bg-amber-950 text-amber-300 border border-amber-800"
                            : "bg-slate-800 text-slate-300"
                        }`}
                      >
                        {j.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-400">{j.stage}</td>
                    <td className="py-2.5 px-3 text-slate-500">
                      {new Date(j.created_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          type="button"
                          onClick={() => onSelectJob(j)}
                          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                          title="View job logs"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        {j.status === "RUNNING" && (
                          <button
                            type="button"
                            onClick={() => onCancel(j.id)}
                            className="p-1 rounded text-red-400 hover:text-red-200 hover:bg-red-900/40 transition-colors"
                            title="Cancel job"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
