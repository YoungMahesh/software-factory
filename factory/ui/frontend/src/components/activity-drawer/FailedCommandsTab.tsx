import React, { useState, useEffect, useMemo } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { FailedCommand, Job } from "../../types";
import { CommandCard } from "../CommandCard";

export interface FailedCommandsTabProps {
  failedCommands: FailedCommand[];
  activeJobId?: string;
  jobs?: Job[];
  selectedRepo?: string;
  onSelectJob?: (job: Job) => void;
}

export type StageFilter = "ALL" | "CODER" | "VERIFIER";

export const FailedCommandsTab: React.FC<FailedCommandsTabProps> = ({
  failedCommands,
  activeJobId,
  jobs = [],
  selectedRepo,
  onSelectJob,
}) => {
  const [selectedJobId, setSelectedJobId] = useState<string>(activeJobId || "");
  const [stageFilter, setStageFilter] = useState<StageFilter>("ALL");
  const [historicalCommands, setHistoricalCommands] = useState<FailedCommand[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Sync selectedJobId if activeJobId updates
  useEffect(() => {
    if (activeJobId) {
      setSelectedJobId(activeJobId);
    }
  }, [activeJobId]);

  // Fetch historical failed commands when inspecting a non-active past job
  useEffect(() => {
    if (!selectedJobId || selectedJobId === activeJobId) {
      setHistoricalCommands([]);
      setIsLoading(false);
      setError(null);
      return;
    }

    let isMounted = true;
    setIsLoading(true);
    setError(null);

    fetch(`/api/jobs/${encodeURIComponent(selectedJobId)}/failed-commands`)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`Failed to load historical failed commands: HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (isMounted) {
          setHistoricalCommands(data.failed_commands || []);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || "Failed to load historical failed commands");
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedJobId, activeJobId]);

  // Filter jobs by current repo
  const repoJobs = useMemo(() => {
    const list = jobs.filter((j) => !selectedRepo || !j.repo || j.repo === selectedRepo);
    if (activeJobId && !list.some((j) => j.id === activeJobId)) {
      return [{ id: activeJobId, status: "RUNNING", stage: "CODER" } as Job, ...list];
    }
    return list;
  }, [jobs, selectedRepo, activeJobId]);

  const isViewingActive = !selectedJobId || selectedJobId === activeJobId;
  const currentCommands = isViewingActive ? failedCommands : historicalCommands;

  // Calculate failure counts per stage
  const totalCount = currentCommands.length;
  const coderCount = currentCommands.filter((c) => (c.stage || "").toUpperCase() === "CODER").length;
  const verifierCount = currentCommands.filter((c) => (c.stage || "").toUpperCase() === "VERIFIER").length;

  // Filter commands by active stage filter chip
  const displayedCommands = useMemo(() => {
    if (stageFilter === "CODER") {
      return currentCommands.filter((c) => (c.stage || "").toUpperCase() === "CODER");
    }
    if (stageFilter === "VERIFIER") {
      return currentCommands.filter((c) => (c.stage || "").toUpperCase() === "VERIFIER");
    }
    return currentCommands;
  }, [currentCommands, stageFilter]);

  const handleJobChange = (jobId: string) => {
    setSelectedJobId(jobId);
    if (onSelectJob) {
      const targetJob = repoJobs.find((j) => j.id === jobId);
      if (targetJob) {
        onSelectJob(targetJob);
      }
    }
  };

  return (
    <div className="space-y-4">
      {/* Tab Sub-Header: Stage Filter Chips & Past-Run Selector Dropdown */}
      <div
        id="failed-commands-tab-header"
        data-testid="failed-commands-tab-header"
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-hairline"
      >
        {/* Stage Filter Chips */}
        <div className="flex items-center space-x-1.5" role="group" aria-label="Stage filters">
          <button
            type="button"
            id="stage-filter-all"
            data-testid="stage-filter-all"
            onClick={() => setStageFilter("ALL")}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
              stageFilter === "ALL"
                ? "bg-primary text-white shadow-xs"
                : "bg-white text-muted hover:text-ink border border-hairline hover:bg-soft-stone"
            }`}
          >
            <span>All</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${
                stageFilter === "ALL" ? "bg-white/20 text-white" : "bg-soft-stone text-muted"
              }`}
            >
              {totalCount}
            </span>
          </button>

          <button
            type="button"
            id="stage-filter-coder"
            data-testid="stage-filter-coder"
            onClick={() => setStageFilter("CODER")}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
              stageFilter === "CODER"
                ? "bg-primary text-white shadow-xs"
                : "bg-white text-muted hover:text-ink border border-hairline hover:bg-soft-stone"
            }`}
          >
            <span>Coder</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${
                stageFilter === "CODER" ? "bg-white/20 text-white" : "bg-soft-stone text-muted"
              }`}
            >
              {coderCount}
            </span>
          </button>

          <button
            type="button"
            id="stage-filter-verifier"
            data-testid="stage-filter-verifier"
            onClick={() => setStageFilter("VERIFIER")}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
              stageFilter === "VERIFIER"
                ? "bg-primary text-white shadow-xs"
                : "bg-white text-muted hover:text-ink border border-hairline hover:bg-soft-stone"
            }`}
          >
            <span>Verifier</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${
                stageFilter === "VERIFIER" ? "bg-white/20 text-white" : "bg-soft-stone text-muted"
              }`}
            >
              {verifierCount}
            </span>
          </button>
        </div>

        {/* Past-Run Selector Dropdown */}
        <div className="flex items-center space-x-2">
          <label
            htmlFor="failed-commands-job-selector"
            className="text-[11px] font-medium text-muted font-sans shrink-0"
          >
            Run:
          </label>
          <select
            id="failed-commands-job-selector"
            data-testid="failed-commands-job-selector"
            value={selectedJobId}
            onChange={(e) => handleJobChange(e.target.value)}
            className="bg-white border border-hairline rounded-pill px-2.5 py-1 text-xs text-ink font-mono focus:outline-none focus:ring-1 focus:ring-form-focus shadow-2xs max-w-[220px] truncate"
          >
            {repoJobs.length === 0 ? (
              <option value="">No runs available</option>
            ) : (
              repoJobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.id}
                  {j.id === activeJobId ? " (Active)" : ""}
                  {j.status ? ` - ${j.status}` : ""}
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div
          data-testid="failed-commands-loading"
          className="flex items-center justify-center py-16 space-x-2 text-xs text-muted font-mono"
        >
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
          <span>Loading failed commands...</span>
        </div>
      )}

      {/* Error state */}
      {!isLoading && error && (
        <div
          data-testid="failed-commands-error"
          className="p-4 rounded-lg bg-coral/10 border border-coral/30 text-center text-xs text-coral font-mono"
        >
          {error}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && displayedCommands.length === 0 && (
        <div
          data-testid="failed-commands-empty-state"
          id="failed-commands-empty-state"
          className="flex flex-col items-center justify-center py-16 px-4 text-center space-y-3"
        >
          <div className="w-12 h-12 rounded-full bg-pale-green/40 border border-deep-green/20 flex items-center justify-center text-deep-green shadow-xs">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-ink font-sans">
              No Failed Commands
            </h3>
            <p className="text-xs text-muted max-w-sm leading-relaxed">
              {stageFilter === "ALL"
                ? "All shell commands executed successfully during Coder Agent and Deterministic Verifier stages. Zero command failures detected."
                : `No command failures detected in the ${
                    stageFilter === "CODER" ? "Coder Agent" : "Deterministic Verifier"
                  } stage.`}
            </p>
          </div>
        </div>
      )}

      {/* Filtered failed command list */}
      {!isLoading && !error && displayedCommands.length > 0 && (
        <div id="studio-drawer-failed-commands" className="space-y-3">
          {displayedCommands.map((cmd) => (
            <CommandCard
              key={cmd.id}
              id={`failed-cmd-${cmd.id}`}
              command={cmd.command}
              cwd={cmd.cwd}
              stage={cmd.stage}
              exitCode={cmd.exitCode ?? cmd.exit_code}
              isError={cmd.isError ?? cmd.is_error}
              durationMs={cmd.durationMs ?? cmd.duration_ms}
              output={cmd.output || cmd.stdout || ""}
              stderr={cmd.stderr}
            />
          ))}
        </div>
      )}
    </div>
  );
};
