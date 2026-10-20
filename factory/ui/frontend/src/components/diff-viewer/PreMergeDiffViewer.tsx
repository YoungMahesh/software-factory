import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  GitBranch,
  RefreshCw,
  CheckCircle2,
  Columns2,
  AlignJustify,
  FolderGit2,
  AlertCircle,
} from "lucide-react";
import { DiffScope, DiffLayout } from "../../types";
import { fetchRepoDiff } from "../../api";
import { DiffFileCard } from "./DiffFileCard";

interface PreMergeDiffViewerProps {
  repo?: string;
  branch?: string;
  base?: string;
}

export const PreMergeDiffViewer: React.FC<PreMergeDiffViewerProps> = ({
  repo = "",
  branch = "main",
  base = "main",
}) => {
  const [scope, setScope] = useState<DiffScope>("working_tree");
  const [layout, setLayout] = useState<DiffLayout>("unified");
  const [expandedFiles, setExpandedFiles] = useState<Record<string, boolean>>({});

  const {
    data: diffData,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["repo-diff", repo, scope, branch, base],
    queryFn: () => fetchRepoDiff(repo, scope, branch, base),
    enabled: Boolean(repo),
  });

  const files = diffData?.files || [];
  const summary = diffData?.summary || { total_files: 0, additions: 0, deletions: 0 };
  const isClean = diffData?.clean || files.length === 0;

  const toggleFile = (path: string) => {
    setExpandedFiles((prev) => ({
      ...prev,
      [path]: prev[path] !== undefined ? !prev[path] : false,
    }));
  };

  const isFileExpanded = (path: string) => {
    return expandedFiles[path] !== undefined ? expandedFiles[path] : true;
  };

  const toggleAll = (expand: boolean) => {
    const updated: Record<string, boolean> = {};
    for (const f of files) {
      updated[f.path] = expand;
    }
    setExpandedFiles(updated);
  };

  return (
    <div
      data-testid="pre-merge-diff-viewer"
      className="flex-1 min-h-0 flex flex-col bg-stone-50 rounded-2xl border border-hairline overflow-hidden shadow-2xs"
    >
      {/* Scope Selector and Toolbar Banner */}
      <div className="shrink-0 p-3.5 bg-white border-b border-hairline flex flex-wrap items-center justify-between gap-3">
        {/* Scope Selector: Working Tree Changes vs Branch Changes */}
        <div
          data-testid="diff-scope-selector"
          className="inline-flex items-center p-1 rounded-pill bg-soft-stone/70 border border-hairline space-x-1"
        >
          <button
            data-testid="diff-scope-working_tree"
            type="button"
            onClick={() => setScope("working_tree")}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              scope === "working_tree"
                ? "bg-primary text-white shadow-xs"
                : "text-slate-600 hover:text-ink hover:bg-white/60"
            }`}
          >
            <FolderGit2 className="w-3.5 h-3.5" />
            <span>Working Tree Changes</span>
          </button>

          <button
            data-testid="diff-scope-branch"
            type="button"
            onClick={() => setScope("branch")}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              scope === "branch"
                ? "bg-primary text-white shadow-xs"
                : "text-slate-600 hover:text-ink hover:bg-white/60"
            }`}
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span>Branch Changes</span>
          </button>
        </div>

        {/* Layout Switcher (Unified vs Split) and Actions */}
        <div className="flex items-center space-x-2">
          <div className="inline-flex items-center p-1 rounded-pill bg-soft-stone/70 border border-hairline space-x-1">
            <button
              data-testid="layout-toggle-unified"
              type="button"
              onClick={() => setLayout("unified")}
              title="Unified hunk view"
              className={`flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
                layout === "unified"
                  ? "bg-primary text-white shadow-xs"
                  : "text-slate-600 hover:text-ink hover:bg-white/60"
              }`}
            >
              <AlignJustify className="w-3.5 h-3.5" />
              <span>Unified</span>
            </button>

            <button
              data-testid="layout-toggle-split"
              type="button"
              onClick={() => setLayout("split")}
              title="Split two-column side-by-side view"
              className={`flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-medium transition-all cursor-pointer ${
                layout === "split"
                  ? "bg-primary text-white shadow-xs"
                  : "text-slate-600 hover:text-ink hover:bg-white/60"
              }`}
            >
              <Columns2 className="w-3.5 h-3.5" />
              <span>Split</span>
            </button>
          </div>

          <button
            data-testid="diff-refresh-btn"
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1.5 rounded-pill border border-hairline bg-white hover:bg-soft-stone/50 text-slate-500 hover:text-ink transition-colors cursor-pointer"
            title="Refresh diffs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Summary Statistics Sub-Header */}
      <div className="shrink-0 px-4 py-2.5 bg-white/60 border-b border-hairline flex items-center justify-between text-xs">
        <div className="flex items-center space-x-3">
          <span
            data-testid="diff-summary-files"
            className="font-semibold text-ink font-mono"
          >
            {summary.total_files} modified file{summary.total_files === 1 ? "" : "s"}
          </span>

          <div className="flex items-center space-x-1.5 font-mono">
            <span
              data-testid="diff-summary-additions"
              className="inline-flex items-center text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full font-medium text-[11px] border border-emerald-200/60"
            >
              +{summary.additions}
            </span>
            <span
              data-testid="diff-summary-deletions"
              className="inline-flex items-center text-coral bg-coral/10 px-2 py-0.5 rounded-full font-medium text-[11px] border border-coral/20"
            >
              -{summary.deletions}
            </span>
          </div>

          <span className="text-slate-400 text-[11px] hidden sm:inline">
            {scope === "working_tree"
              ? "Uncommitted live container edits"
              : `Comparing ${branch} against ${base}`}
          </span>
        </div>

        {files.length > 0 && (
          <div className="flex items-center space-x-2 text-[11px] text-slate-500">
            <button
              type="button"
              onClick={() => toggleAll(true)}
              className="hover:text-ink underline cursor-pointer"
            >
              Expand all
            </button>
            <span>•</span>
            <button
              type="button"
              onClick={() => toggleAll(false)}
              className="hover:text-ink underline cursor-pointer"
            >
              Collapse all
            </button>
          </div>
        )}
      </div>

      {/* Main Diff Content Area */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {isLoading ? (
          <div className="h-64 flex flex-col items-center justify-center space-y-3 text-slate-400">
            <RefreshCw className="w-6 h-6 animate-spin text-slate-400" />
            <p className="text-xs">Computing Git diff comparison...</p>
          </div>
        ) : isError ? (
          <div className="p-6 bg-red-50/50 rounded-2xl border border-red-200 text-center">
            <AlertCircle className="w-8 h-8 text-coral mx-auto mb-2" />
            <h4 className="text-xs font-semibold text-coral mb-1">Failed to Load Diff</h4>
            <p className="text-xs text-slate-600 mb-3">
              {(error as any)?.message || "Could not retrieve git differences."}
            </p>
            <button
              type="button"
              onClick={() => refetch()}
              className="px-3 py-1 rounded-pill bg-primary text-white text-xs font-medium cursor-pointer"
            >
              Retry
            </button>
          </div>
        ) : isClean ? (
          <div
            data-testid="diff-empty-state"
            className="flex flex-col items-center justify-center text-center p-12 bg-white rounded-2xl border border-hairline shadow-2xs my-4"
          >
            <div className="w-12 h-12 rounded-full bg-pale-green/10 text-pale-green flex items-center justify-center mb-3">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-ink mb-1">
              {scope === "working_tree"
                ? "No Working Tree Changes"
                : "No Branch Changes"}
            </h3>
            <p className="text-xs text-slate-500 max-w-sm">
              {scope === "working_tree"
                ? "Container filesystem is clean. All modifications have been committed to the branch."
                : `Feature branch is up to date with the default trunk (${base}). No differences detected.`}
            </p>
          </div>
        ) : (
          files.map((file) => (
            <DiffFileCard
              key={file.path}
              file={file}
              layout={layout}
              isExpanded={isFileExpanded(file.path)}
              onToggle={() => toggleFile(file.path)}
            />
          ))
        )}
      </div>
    </div>
  );
};
