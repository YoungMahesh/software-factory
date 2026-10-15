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
