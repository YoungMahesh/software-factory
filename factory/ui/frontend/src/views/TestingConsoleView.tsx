import React from "react";
import {
  RotateCw,
  Box,
  History,
  XCircle,
  Eye,
  Lock,
} from "lucide-react";
import { Repo, Job, LaunchJobParams } from "../types";
import { StageStepper } from "../components/StageStepper";
import { TerminalLogViewer } from "../components/TerminalLogViewer";
import { JobConfigPanel } from "../components/console/JobConfigPanel";
import { Badge } from "../components/ui/Badge";

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
  return (
    <div id="console-view" className="flex flex-col space-y-6 max-w-7xl mx-auto px-4 py-6">
      {/* Top Controls Grid: Launch Form & Repository Selection */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Repository Selection */}
        <div className="lg:col-span-1 bg-soft-stone rounded-xl border border-hairline p-5 space-y-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink font-sans flex items-center space-x-2">
              <Box className="w-4 h-4 text-primary" />
              <span>Target Repository</span>
              {repos.find((r) => r.name === selectedRepo)?.private && (
                <span
                  data-testid="console-repo-private-badge"
                  className="flex items-center text-[10px] font-medium px-2 py-0.5 rounded-pill bg-white text-ink border border-hairline space-x-1 shadow-2xs"
                  title="Private repository"
                >
                  <Lock className="w-2.5 h-2.5 text-muted" />
                  <span>Private</span>
                </span>
              )}
            </h2>
            <button
              id="btn-refresh-repos"
              type="button"
              onClick={onRefreshRepos}
              className="p-1.5 rounded-pill text-muted hover:text-ink hover:bg-white transition-colors cursor-pointer"
              title="Refresh repositories"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1.5">
              Organization Repositories
            </label>
            <select
              id="select-repo"
              value={selectedRepo}
              onChange={(e) => onSelectRepo(e.target.value)}
              className="w-full bg-white border border-hairline rounded-pill px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-form-focus shadow-2xs"
            >
              <option value="">Select a repository...</option>
              {repos.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name} {r.is_tanstack_compatible ? "✦ (TanStack)" : ""}{r.private ? " 🔒" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Right Columns: Job Configuration & Parameters Panel */}
        <div className="lg:col-span-2">
          <JobConfigPanel
            selectedRepo={selectedRepo}
            onLaunch={onLaunch}
            activeJob={activeJob}
            onCancel={onCancel}
          />
        </div>
      </div>

      {/* Live Pipeline Execution Feature Band */}
      <div className="rounded-[22px] bg-deep-green p-6 border border-deep-green/60 shadow-xl space-y-6 text-white">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <h2 className="text-sm font-semibold text-white tracking-wide font-sans">
              Execution Telemetry & Pipeline
            </h2>
          </div>
          {activeJob && (
            <span className="text-xs font-mono text-pale-green/90 bg-white/10 px-2.5 py-0.5 rounded-pill border border-white/10">
              Job: {activeJob.id}
            </span>
          )}
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
      </div>

      {/* Job History Table */}
      <div className="bg-soft-stone rounded-xl border border-hairline p-5 shadow-2xs">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-ink font-sans flex items-center space-x-2">
            <History className="w-4 h-4 text-primary" />
            <span>Job History</span>
          </h2>
          <span id="history-count" className="text-xs font-mono text-muted">
            {jobs.length} jobs
          </span>
        </div>

        <div className="overflow-x-auto bg-white rounded-lg border border-hairline">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-hairline text-[11px] font-mono text-muted bg-soft-stone/40">
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
            <tbody id="history-table-body" className="divide-y divide-hairline font-mono">
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-muted italic">
                    No jobs recorded.
                  </td>
                </tr>
              ) : (
                jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-soft-stone/30 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-primary">{j.id}</td>
                    <td className="py-2.5 px-3 text-ink">{j.repo}</td>
                    <td className="py-2.5 px-3 text-muted">{j.feature || "—"}</td>
                    <td className="py-2.5 px-3">
                      <Badge
                        variant={
                          j.status === "SUCCESS"
                            ? "success"
                            : j.status === "FAILED"
                            ? "danger"
                            : j.status === "RUNNING"
                            ? "console"
                            : "neutral"
                        }
                      >
                        {j.status}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3 text-muted">{j.stage}</td>
                    <td className="py-2.5 px-3 text-muted">
                      {new Date(j.created_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          type="button"
                          onClick={() => onSelectJob(j)}
                          className="p-1 rounded-pill text-muted hover:text-ink hover:bg-soft-stone transition-colors cursor-pointer"
                          title="View job logs"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        {j.status === "RUNNING" && (
                          <button
                            type="button"
                            onClick={() => onCancel(j.id)}
                            className="p-1 rounded-pill text-coral hover:text-white hover:bg-coral transition-colors cursor-pointer"
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
