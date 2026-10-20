import React from "react";
import { ChevronDown, ChevronRight, FileCode } from "lucide-react";
import { FileDiffItem, DiffLayout } from "../../types";
import { DiffSplitView, renderTokenizedLine } from "./DiffSplitView";
import { DiffStatsBadges } from "./DiffStatsBadges";

interface DiffFileCardProps {
  file: FileDiffItem;
  layout: DiffLayout;
  isExpanded: boolean;
  onToggle: () => void;
}

export const DiffFileCard: React.FC<DiffFileCardProps> = ({
  file,
  layout,
  isExpanded,
  onToggle,
}) => {
  const getStatusBadge = (status: FileDiffItem["status"]) => {
    switch (status) {
      case "added":
        return (
          <span className="px-2 py-0.5 rounded-pill text-[10px] font-mono font-medium bg-pale-green/20 text-deep-green border border-deep-green/20">
            added
          </span>
        );
      case "deleted":
        return (
          <span className="px-2 py-0.5 rounded-pill text-[10px] font-mono font-medium bg-coral/10 text-coral border border-coral/20">
            deleted
          </span>
        );
      case "renamed":
        return (
          <span className="px-2 py-0.5 rounded-pill text-[10px] font-mono font-medium bg-amber-400/10 text-amber-500 border border-amber-400/20">
            renamed
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded-pill text-[10px] font-mono font-medium bg-slate-100 text-slate-600 border border-slate-200">
            modified
          </span>
        );
    }
  };

  const renderUnifiedView = () => {
    const rawLines = file.patch ? file.patch.split(/\r?\n/) : [];

    return (
      <div
        data-testid={`unified-diff-${file.path}`}
        className="p-3 font-mono text-[11px] leading-relaxed max-h-[480px] overflow-y-auto bg-primary border-t border-white/10 select-text"
      >
        {rawLines.map((line, idx) => {
          if (
            line.startsWith("--- ") ||
            line.startsWith("+++ ") ||
            line.startsWith("diff ") ||
            line.startsWith("index ")
          ) {
            return (
              <div key={idx} className="text-slate-500 font-bold px-2.5 py-0.5 whitespace-pre-wrap break-all">
                {line}
              </div>
            );
          }

          if (line.startsWith("@@")) {
            return (
              <div key={idx} className="text-slate-300 bg-white/5 px-2.5 py-0.5 my-1 rounded border-y border-white/5 whitespace-pre-wrap break-all">
                {line}
              </div>
            );
          }

          if (line.startsWith("+")) {
            return (
              <div key={idx} className="diff-addition text-pale-green bg-pale-green/10 px-2.5 py-0.5 border-l-2 border-pale-green whitespace-pre-wrap break-all">
                +{renderTokenizedLine(line.slice(1))}
              </div>
            );
          }

          if (line.startsWith("-")) {
            return (
              <div key={idx} className="diff-deletion text-coral bg-coral/10 px-2.5 py-0.5 border-l-2 border-coral whitespace-pre-wrap break-all">
                -{renderTokenizedLine(line.slice(1))}
              </div>
            );
          }

          const content = line.startsWith(" ") ? line.slice(1) : line;
          return (
            <div key={idx} className="text-slate-300 px-2.5 py-0.5 whitespace-pre-wrap break-all">
              {renderTokenizedLine(content)}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div
      data-testid={`diff-card-${file.path}`}
      className="rounded-2xl border border-hairline bg-white shadow-2xs overflow-hidden transition-all duration-200"
    >
      {/* File Card Header Accordion Toggle */}
      <button
        data-testid={`diff-card-toggle-${file.path}`}
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-soft-stone/40 text-left transition-colors cursor-pointer select-none"
      >
        <div className="flex items-center space-x-2.5 min-w-0 pr-3">
          <div className="text-slate-400 shrink-0">
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-slate-600" />
            ) : (
              <ChevronRight className="w-4 h-4 text-slate-600" />
            )}
          </div>
          <FileCode className="w-4 h-4 text-slate-500 shrink-0" />
          <span className="font-mono text-xs font-semibold text-ink truncate">
            {file.path}
          </span>
          {getStatusBadge(file.status)}
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          <DiffStatsBadges
            additions={file.additions}
            deletions={file.deletions}
            additionsTestId={`file-additions-${file.path}`}
            deletionsTestId={`file-deletions-${file.path}`}
          />
        </div>
      </button>

      {/* Expandable Diff Content (Unified vs Split) */}
      {isExpanded && (
        <div>
          {layout === "unified" ? (
            renderUnifiedView()
          ) : (
            <div data-testid={`split-diff-${file.path}`}>
              <DiffSplitView patch={file.patch} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};
